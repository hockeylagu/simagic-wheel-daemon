"""
LMU (Le Mans Ultimate) Reader
Reads active vehicle, track, and session state from:
1. Embedded HTTP REST API (http://127.0.0.1:6397/navigation/state & /rest/watch/standings)
2. rFactor 2 Shared Memory Mapped File ($rFactor2SMMP_Scoring$)

Fetching and parsing are separate: the parse_* functions are pure, so raw data captured
with `simagic-daemon --capture` can be replayed through exactly the same code.

100% read-only, non-intrusive, zero anti-cheat risk.
"""

import mmap
import urllib.request
import urllib.error
import json
import struct
import sys
import logging
from typing import Optional, Dict, Any, Sequence

logger = logging.getLogger("simagic_daemon.lmu_reader")


# 127.0.0.1 instead of localhost: on Windows "localhost" tries IPv6 (::1) first, which adds
# a ~2s delay per request whenever LMU is not running.
LMU_REST_NAV_URL = "http://127.0.0.1:6397/navigation/state"
LMU_REST_STANDINGS_URL = "http://127.0.0.1:6397/rest/watch/standings"
LMU_REST_TIMEOUT = 0.8

# Standings field names vary between LMU builds; try them in order.
STANDINGS_PLAYER_KEYS = ("player", "isPlayer", "is_player")
STANDINGS_VEHICLE_KEYS = ("vehicleFilename", "vehFile", "carType", "vehicleName", "vehicle")
STANDINGS_CLASS_KEYS = ("carClass", "vehicleClass", "class")

# rF2 Shared Memory Map plugin layout (rF2State.h, #pragma pack(4)); offsets cross-checked
# against LMULapTime's tools/telemetry-recorder/Rf2Structs.cs (all match, total 75312 bytes):
#   rF2Scoring = version block (8) + mBytesUpdatedHint (4) + rF2ScoringInfo (548)
#                + rF2VehicleScoring[128] (584 each)
SCORING_BUFFER_NAME = "$rFactor2SMMP_Scoring$"
MAX_MAPPED_VEHICLES = 128
SCORING_INFO_OFFSET = 12
SI_TRACK_NAME = 0              # char mTrackName[64]
SI_NUM_VEHICLES = 104          # long mNumVehicles
SCORING_INFO_SIZE = 548
SCORING_VEHICLES_OFFSET = SCORING_INFO_OFFSET + SCORING_INFO_SIZE
VEHICLE_SCORING_SIZE = 584
VS_VEHICLE_NAME = 36           # char mVehicleName[64]
VS_IS_PLAYER = 196             # bool mIsPlayer
VS_VEHICLE_CLASS = 200         # char mVehicleClass[32]
SCORING_BUFFER_SIZE = SCORING_VEHICLES_OFFSET + MAX_MAPPED_VEHICLES * VEHICLE_SCORING_SIZE


def _shared_memory_exists(name: str) -> bool:
    """
    True if a named file mapping already exists. mmap.mmap() with a tagname would otherwise
    CREATE the mapping when LMU is not running, and a pre-created section of the wrong size
    can prevent the rF2 plugin from mapping its own buffer later.
    """
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.OpenFileMappingW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    FILE_MAP_READ = 0x0004
    handle = kernel32.OpenFileMappingW(FILE_MAP_READ, False, name)
    if not handle:
        return False
    kernel32.CloseHandle(handle)
    return True


def _c_string(data: bytes, offset: int, length: int) -> str:
    """Decodes a NUL-terminated fixed-size C string."""
    return data[offset:offset + length].split(b"\x00")[0].decode("latin1", errors="ignore").strip()


def _first_value(entry: Dict[str, Any], keys: Sequence[str]) -> str:
    """Returns the first non-empty string value among the given keys."""
    for key in keys:
        value = entry.get(key)
        if value:
            return str(value)
    return ""


def _is_player_entry(entry: Dict[str, Any]) -> bool:
    return any(entry.get(key) is True for key in STANDINGS_PLAYER_KEYS)


def fetch_json(url: str, timeout: float = LMU_REST_TIMEOUT) -> Optional[Any]:
    """GETs a JSON document from LMU's REST API. Returns None if unreachable or invalid."""
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.debug(f"[LMU REST] {url} unavailable ({e})")
        return None


# -----------------------------------------------------------------------------
# Pure parsers (also used to replay captures)
# -----------------------------------------------------------------------------
def parse_nav_state(data: Any) -> Optional[Dict[str, Any]]:
    """Extracts the selected car from a /navigation/state document."""
    if not isinstance(data, dict):
        return None
    loading_data_raw = (data.get("loadingStatus") or {}).get("loadingData")
    if not loading_data_raw:
        return None
    try:
        loading_data = json.loads(loading_data_raw) if isinstance(loading_data_raw, str) else loading_data_raw
    except ValueError:
        return None
    selected_car = loading_data.get("selectedCar") if isinstance(loading_data, dict) else None
    if not selected_car:
        return None

    veh_file = selected_car.get("vehFile", "")
    manufacturer = selected_car.get("manufacturer", "")
    identifier = veh_file or manufacturer
    if not identifier:
        return None
    return {
        "source": "REST_NAV_STATE",
        "identifier": identifier,
        "veh_file": veh_file,
        "manufacturer": manufacturer,
        "classes": selected_car.get("classes", []),
        "team": selected_car.get("team", ""),
        "number": selected_car.get("number", ""),
    }


def parse_standings(data: Any) -> Optional[Dict[str, Any]]:
    """Extracts the player's own car from a /rest/watch/standings document."""
    if not isinstance(data, list):
        return None
    player = next((e for e in data if isinstance(e, dict) and _is_player_entry(e)), None)
    if player is None:
        return None
    veh = _first_value(player, STANDINGS_VEHICLE_KEYS)
    if not veh:
        return None
    return {
        "source": "REST_STANDINGS",
        "identifier": veh,
        "car_type": player.get("carType", ""),
        "driver_name": player.get("driverName", ""),
        "car_number": player.get("carNumber", ""),
        "class": _first_value(player, STANDINGS_CLASS_KEYS),
    }


def scoring_buffer_consistent(data: bytes) -> bool:
    """False if the plugin was mid-write (version begin/end counters differ) or data is truncated."""
    if len(data) < SCORING_VEHICLES_OFFSET:
        return False
    begin, end = struct.unpack_from("<II", data, 0)
    return begin == end


def parse_scoring_buffer(data: bytes) -> Optional[Dict[str, Any]]:
    """
    Parses an rF2Scoring buffer and returns the player's vehicle (record with mIsPlayer set).
    Returns a track-only dict if no player vehicle is found, or None if the data is implausible.
    """
    if len(data) < SCORING_VEHICLES_OFFSET:
        return None

    track_name = _c_string(data, SCORING_INFO_OFFSET + SI_TRACK_NAME, 64)
    num_vehicles = struct.unpack_from("<i", data, SCORING_INFO_OFFSET + SI_NUM_VEHICLES)[0]
    if not 0 <= num_vehicles <= MAX_MAPPED_VEHICLES:
        logger.debug(f"[LMU SHM] Implausible mNumVehicles={num_vehicles}; layout mismatch, ignoring buffer")
        return None

    for i in range(num_vehicles):
        base = SCORING_VEHICLES_OFFSET + i * VEHICLE_SCORING_SIZE
        if base + VEHICLE_SCORING_SIZE > len(data):
            break
        if not data[base + VS_IS_PLAYER]:
            continue
        vehicle_name = _c_string(data, base + VS_VEHICLE_NAME, 64)
        if not vehicle_name:
            break
        return {
            "source": "SHARED_MEMORY",
            "identifier": vehicle_name,
            "class": _c_string(data, base + VS_VEHICLE_CLASS, 32),
            "track_name": track_name,
        }

    if track_name:
        return {
            "source": "SHARED_MEMORY_TRACK_ONLY",
            "identifier": "",
            "track_name": track_name,
        }
    return None


# -----------------------------------------------------------------------------
# Live reader
# -----------------------------------------------------------------------------
class LMUReader:
    """Reader for Le Mans Ultimate game and vehicle state."""

    def __init__(self):
        self.scoring_mmap: Optional[mmap.mmap] = None
        self._standings_keys_logged = False

    def is_rest_api_online(self) -> bool:
        """Checks if LMU's embedded REST API responds."""
        return fetch_json(LMU_REST_NAV_URL) is not None

    def get_rest_vehicle(self) -> Optional[Dict[str, Any]]:
        """
        Queries LMU REST API for the currently selected or active car.
        Checks /navigation/state loadingData first, then the player's entry in /rest/watch/standings.
        """
        veh = parse_nav_state(fetch_json(LMU_REST_NAV_URL))
        if veh:
            return veh

        standings = fetch_json(LMU_REST_STANDINGS_URL)
        if isinstance(standings, list) and standings and isinstance(standings[0], dict):
            if not self._standings_keys_logged:
                logger.debug(f"[LMU REST] Standings entry fields: {sorted(standings[0].keys())}")
                self._standings_keys_logged = True
            veh = parse_standings(standings)
            if veh is None:
                logger.debug("[LMU REST] Standings has no usable entry flagged as the player; ignoring it")
            return veh
        return None

    def connect_shared_memory(self) -> bool:
        """Opens the shared memory mapped file created by the rF2 Shared Memory Map plugin, if it exists."""
        if self.scoring_mmap is not None:
            return True
        # Session-local name first, then the Global\ namespace (same order as LMULapTime's recorder)
        for name in (SCORING_BUFFER_NAME, "Global\\" + SCORING_BUFFER_NAME):
            if not _shared_memory_exists(name):
                continue
            try:
                self.scoring_mmap = mmap.mmap(0, SCORING_BUFFER_SIZE, name, access=mmap.ACCESS_READ)
                return True
            except (FileNotFoundError, OSError):
                self.scoring_mmap = None
        return False

    def close_shared_memory(self):
        """Closes the shared memory handle."""
        if self.scoring_mmap:
            try:
                self.scoring_mmap.close()
            except Exception:
                pass
            self.scoring_mmap = None

    def read_scoring_raw(self) -> Optional[bytes]:
        """Reads a consistent copy of the scoring buffer (the plugin may be mid-write)."""
        if not self.connect_shared_memory():
            return None
        try:
            for _ in range(3):
                self.scoring_mmap.seek(0)
                data = self.scoring_mmap.read(SCORING_BUFFER_SIZE)
                if scoring_buffer_consistent(data):
                    return data
        except Exception as e:
            logger.debug(f"[LMU SHM] Failed to read scoring buffer: {e}")
        return None

    def get_shared_memory_vehicle(self) -> Optional[Dict[str, Any]]:
        """Reads the player vehicle from rFactor 2 shared memory ($rFactor2SMMP_Scoring$)."""
        data = self.read_scoring_raw()
        if data is None:
            return None
        try:
            return parse_scoring_buffer(data)
        except Exception as e:
            logger.debug(f"[LMU SHM] Failed to parse scoring buffer: {e}")
            return None

    def get_active_vehicle(self) -> Optional[Dict[str, Any]]:
        """
        Unified method to detect active car in LMU.
        Prioritizes REST API (most descriptive) with Shared Memory as fallback.
        """
        # 1. Try REST API
        veh = self.get_rest_vehicle()
        if veh and veh.get("identifier"):
            return veh

        # 2. Try Shared Memory
        veh = self.get_shared_memory_vehicle()
        if veh and veh.get("identifier"):
            return veh

        return None


if __name__ == "__main__":
    reader = LMUReader()
    print("Testing LMU Connection...")
    print(f"REST API online: {reader.is_rest_api_online()}")
    print(f"Shared Memory available: {reader.connect_shared_memory()}")
    veh = reader.get_active_vehicle()
    print(f"Active Vehicle Detected: {veh}")
