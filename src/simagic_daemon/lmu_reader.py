"""
LMU (Le Mans Ultimate) Reader
Reads active vehicle, track, and session state from:
1. Embedded HTTP REST API (http://localhost:6397/navigation/state & /rest/watch/standings)
2. rFactor 2 Shared Memory Mapped File ($rFactor2SMMP_Scoring$)

100% read-only, non-intrusive, zero anti-cheat risk.
"""

import mmap
import urllib.request
import urllib.error
import json
import struct
import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("simagic_daemon.lmu_reader")


LMU_REST_NAV_URL = "http://localhost:6397/navigation/state"
LMU_REST_STANDINGS_URL = "http://localhost:6397/rest/watch/standings"
SCORING_BUFFER_NAME = "$rFactor2SMMP_Scoring$"


class LMUReader:
    """Reader for Le Mans Ultimate game and vehicle state."""

    def __init__(self):
        self.scoring_mmap: Optional[mmap.mmap] = None

    def is_rest_api_online(self) -> bool:
        """Checks if LMU's embedded REST API responds."""
        try:
            req = urllib.request.Request(LMU_REST_NAV_URL, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=0.8) as resp:
                ok = resp.status == 200
                logger.debug(f"[LMU REST] Checked /navigation/state -> HTTP {resp.status}")
                return ok
        except Exception as e:
            logger.debug(f"[LMU REST] /navigation/state offline ({e})")
            return False

    def get_rest_vehicle(self) -> Optional[Dict[str, Any]]:
        """
        Queries LMU REST API for the currently selected or active car.
        Checks /navigation/state loadingData first, then /rest/watch/standings.
        """
        # 1. Check navigation state
        try:
            req = urllib.request.Request(LMU_REST_NAV_URL, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=0.8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                loading_status = data.get("loadingStatus", {})
                loading_data_raw = loading_status.get("loadingData")

                if loading_data_raw:
                    try:
                        loading_data = json.loads(loading_data_raw) if isinstance(loading_data_raw, str) else loading_data_raw
                        selected_car = loading_data.get("selectedCar")
                        if selected_car:
                            veh_file = selected_car.get("vehFile", "")
                            manufacturer = selected_car.get("manufacturer", "")
                            classes = selected_car.get("classes", [])
                            team = selected_car.get("team", "")
                            number = selected_car.get("number", "")
                            identifier = veh_file or manufacturer
                            if identifier:
                                return {
                                    "source": "REST_NAV_STATE",
                                    "identifier": identifier,
                                    "veh_file": veh_file,
                                    "manufacturer": manufacturer,
                                    "classes": classes,
                                    "team": team,
                                    "number": number,
                                }
                    except Exception:
                        pass
        except Exception:
            pass

        # 2. Check live standings (if on-track / driving)
        try:
            req = urllib.request.Request(LMU_REST_STANDINGS_URL, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=0.8) as resp:
                standings = json.loads(resp.read().decode("utf-8"))
                if isinstance(standings, list) and len(standings) > 0:
                    # Look for player or first valid vehicle entry
                    for entry in standings:
                        if isinstance(entry, dict):
                            veh = entry.get("carType") or entry.get("vehicle") or entry.get("vehFile")
                            if veh:
                                return {
                                    "source": "REST_STANDINGS",
                                    "identifier": veh,
                                    "car_type": entry.get("carType", ""),
                                    "driver_name": entry.get("driverName", ""),
                                    "car_number": entry.get("carNumber", ""),
                                    "class": entry.get("vehicleClass", ""),
                                }
        except Exception:
            pass

        return None

    def connect_shared_memory(self) -> bool:
        """Attempts to open the shared memory mapped file created by LMU."""
        if self.scoring_mmap is not None:
            return True
        try:
            self.scoring_mmap = mmap.mmap(0, 32768, SCORING_BUFFER_NAME, access=mmap.ACCESS_READ)
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

    def get_shared_memory_vehicle(self) -> Optional[Dict[str, Any]]:
        """
        Reads the player vehicle from rFactor 2 shared memory ($rFactor2SMMP_Scoring$).
        """
        if not self.connect_shared_memory():
            return None

        try:
            self.scoring_mmap.seek(0)
            data = self.scoring_mmap.read(16384)
            if len(data) < 128:
                return None

            # Track name is at offset 12..76
            track_name = data[12:76].split(b'\x00')[0].decode('latin1', errors='ignore').strip()

            # Scan the buffer for ASCII vehicle names or tokens
            # In rF2Scoring, vehicle records start after the header (~128 bytes)
            # Find printable strings that look like vehicle names or classes
            # Simple heuristic: scan for known tokens or .veh extensions
            raw_text = data.decode('latin1', errors='ignore')
            for ext in ['.veh', '.VEH']:
                pos = raw_text.find(ext)
                if pos != -1:
                    start = max(0, raw_text.rfind('\x00', 0, pos) + 1)
                    veh_file = raw_text[start:pos + len(ext)].strip()
                    if veh_file:
                        return {
                            "source": "SHARED_MEMORY",
                            "identifier": veh_file,
                            "track_name": track_name,
                        }

            if track_name:
                return {
                    "source": "SHARED_MEMORY_TRACK_ONLY",
                    "identifier": "",
                    "track_name": track_name,
                }
        except Exception:
            pass

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
