"""
Simagic Local API Client
Safely interacts with SimPro Manager v3's local REST API without touching raw USB packets.
"""

import urllib.request
import urllib.error
import json
import os
import sqlite3
from typing import Dict, List, Optional, Any

API_BASE_URL = "http://127.0.0.1:4010/simpro/api/v3"
USER_DB_PATH = os.path.expandvars(r"%LOCALAPPDATA%\Simagic\Simpro3\storage\user.db")

# Known Product & Device UUIDs detected on this system
DEFAULT_BASE_PRODUCT_UUID = "17301504"            # Simagic EVO Base (Alpha)
DEFAULT_BASE_DEVICE_UUID = "<BASE_DEVICE_UUID>"  # Persistent Wheelbase UUID


import logging

logger = logging.getLogger("simagic_daemon.client")


def call_simpro_api(endpoint: str, payload: Optional[Dict[str, Any]] = None, timeout: float = 3.0) -> Dict[str, Any]:
    """Sends a POST request to SimPro Manager's local HTTP API."""
    url = f"{API_BASE_URL}/{endpoint}"
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"}
    )
    logger.debug(f"[SimPro API ->] POST {url} | payload: {payload}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            res = json.loads(raw) if raw else {}
            logger.debug(f"[SimPro API <-] HTTP {resp.status} | response status: {res.get('status')}")
            return res
    except urllib.error.URLError as e:
        logger.debug(f"[SimPro API <-] URLError: {e}")
        return {"status": -1, "message": f"Connection error: {e}"}
    except Exception as e:
        logger.debug(f"[SimPro API <-] Unexpected error: {e}")
        return {"status": -1, "message": f"Unexpected error: {e}"}


def list_presets_from_db(product_uuid: Optional[str] = None) -> List[Dict[str, Any]]:
    """Reads user presets directly from the local SQLite database."""
    if not os.path.exists(USER_DB_PATH):
        return []
    
    conn = sqlite3.connect(f"file:{USER_DB_PATH}?mode=ro", uri=True)
    c = conn.cursor()
    if product_uuid:
        c.execute("""
            SELECT presetName, presetUUID, productUUID, deviceUUID, gameList, factoryReset
            FROM preset
            WHERE productUUID = ?
            ORDER BY id ASC
        """, (str(product_uuid),))
    else:
        c.execute("""
            SELECT presetName, presetUUID, productUUID, deviceUUID, gameList, factoryReset
            FROM preset
            ORDER BY productUUID, id ASC
        """)
    
    presets = []
    for name, uuid, prod_uuid, dev_uuid, games, factory_reset in c.fetchall():
        presets.append({
            "name": name,
            "uuid": uuid,
            "product_uuid": prod_uuid,
            "device_uuid": dev_uuid,
            "games": json.loads(games) if games else [],
            "factory_reset": bool(factory_reset)
        })
    conn.close()
    return presets


def list_presets_from_api(
    product_uuid: str = DEFAULT_BASE_PRODUCT_UUID,
    device_uuid: str = DEFAULT_BASE_DEVICE_UUID
) -> List[Dict[str, Any]]:
    """Queries all active presets from the running SimPro Manager process."""
    res = call_simpro_api("preset_get_dev_config_list", {
        "product_uuid": str(product_uuid),
        "device_uuid": str(device_uuid)
    })
    return res.get("result", [])


def switch_preset(
    preset_uuid: str,
    product_uuid: str = DEFAULT_BASE_PRODUCT_UUID,
    device_uuid: str = DEFAULT_BASE_DEVICE_UUID
) -> bool:
    """
    Safely switches the active profile via SimPro Manager.
    100% safe: Uses SimPro's official C++ validation and USB HID pipeline.
    """
    res = call_simpro_api("preset_select_dev_config", {
        "product_uuid": str(product_uuid),
        "device_uuid": str(device_uuid),
        "preset_uuid": str(preset_uuid)
    })
    if res.get("status") == 200:
        return True
    else:
        return False


class SimagicClient:
    """High-level client for SimPro Manager v3."""

    def __init__(
        self,
        base_product_uuid: str = DEFAULT_BASE_PRODUCT_UUID,
        base_device_uuid: str = DEFAULT_BASE_DEVICE_UUID,
        wheel_product_uuid: str = "33947648",
        wheel_device_uuid: str = "33947648"
    ):
        self.base_product_uuid = base_product_uuid
        self.base_device_uuid = base_device_uuid
        self.wheel_product_uuid = wheel_product_uuid
        self.wheel_device_uuid = wheel_device_uuid

    def is_api_running(self) -> bool:
        res = call_simpro_api("get_support_device")
        return res.get("status") == 200

    def get_connected_devices(self) -> List[Dict[str, Any]]:
        res = call_simpro_api("get_device_list")
        return res.get("result", [])

    def select_base_preset(self, preset_uuid: str) -> bool:
        return switch_preset(preset_uuid, self.base_product_uuid, self.base_device_uuid)

    def select_wheel_preset(self, preset_uuid: str) -> bool:
        return switch_preset(preset_uuid, self.wheel_product_uuid, self.wheel_device_uuid)

    def get_selected_base_preset(self) -> Optional[str]:
        res = call_simpro_api("preset_get_selected_dev_config", {
            "product_uuid": self.base_product_uuid,
            "device_uuid": self.base_device_uuid
        })
        return res.get("result", {}).get("preset_uuid") if res.get("status") == 200 else None

    def get_selected_wheel_preset(self) -> Optional[str]:
        res = call_simpro_api("preset_get_selected_dev_config", {
            "product_uuid": self.wheel_product_uuid,
            "device_uuid": self.wheel_device_uuid
        })
        return res.get("result", {}).get("preset_uuid") if res.get("status") == 200 else None



if __name__ == "__main__":
    print("==================================================")
    print("         Simagic WheelDaemon Diagnostic           ")
    print("==================================================")
    
    print("\n[1] Reading saved wheelbase presets from local database:")
    db_presets = list_presets_from_db()
    for p in db_presets:
        print(f"  * [{p['uuid']}] '{p['name']}' (Linked games: {p['games']})")

    print("\n[2] Checking SimPro Manager local REST server on port 4010:")
    api_presets = list_presets_from_api()
    if api_presets:
        print(f"  * SimPro REST API is active! Found {len(api_presets)} presets via API.")
    else:
        print("  * SimPro REST API returned 0 presets or wheel base is currently offline.")

    print("\nDone. When the wheel is connected and powered on, run this script to verify live switching.")
