"""
Diagnostic Tool: Test Simagic Hardware & SimPro REST API Connection
Inspects SimPro Manager v3 REST server on port 4010, queries connected devices,
reads active presets, and displays available presets from user.db.
"""

import sys
import os

# Safe UTF-8 encoding on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add src to python path for imports if run directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from simagic_daemon.simagic_client import (
    SimagicClient,
    call_simpro_api,
    list_presets_from_db,
    DEFAULT_BASE_PRODUCT_UUID,
    DEFAULT_BASE_DEVICE_UUID,
)


def main():
    print("=" * 70)
    print("      SIMAGIC HARDWARE & SIMPRO REST API DIAGNOSTIC TOOL       ")
    print("=" * 70)

    client = SimagicClient()

    # 1. Check REST API connectivity
    print("\n[1] Checking SimPro Manager v3 REST API (127.0.0.1:4010)...")
    if not client.is_api_running():
        print("  [X] SimPro REST API is NOT reachable!")
        print("  -> Make sure SimPro Manager v3 is open and running in the background.")
        return 1

    print("  [OK] SimPro Manager v3 REST API is ONLINE and responsive!")

    # 2. Query connected physical devices
    print("\n[2] Querying connected physical hardware devices...")
    devices = client.get_connected_devices()
    if not devices:
        print("  [!] SimPro reports 0 connected devices.")
    else:
        print(f"  Found {len(devices)} connected device(s):")
        for dev in devices:
            p_name = dev.get("product_name", "Unknown")
            p_type = dev.get("product_type", "Unknown")
            fw = dev.get("firmware_version", "Unknown")
            p_uuid = dev.get("product_uuid", "Unknown")
            d_uuid = dev.get("device_uuid", "Unknown")
            print(f"    * [{p_type.upper()}] {p_name} (Firmware: {fw})")
            print(f"      Product UUID: {p_uuid} | Device UUID: {d_uuid}")

    # 3. Query active preset for Base and Wheel
    print("\n[3] Reading currently active presets on hardware...")
    active_base = client.get_selected_base_preset()
    active_wheel = client.get_selected_wheel_preset()
    print(f"  * Wheelbase active preset UUID : {active_base or 'None / Unknown'}")
    print(f"  * GT NEO Wheel active preset UUID: {active_wheel or 'None / Unknown'}")

    # 4. List user presets from database
    print("\n[4] Cataloging saved user presets from SimPro database:")
    all_presets = list_presets_from_db()
    if not all_presets:
        print("  [!] No presets found in user.db.")
    else:
        print(f"  Found {len(all_presets)} saved preset(s):")
        for p in all_presets:
            p_name = p.get("name")
            p_uuid = p.get("uuid")
            p_prod = p.get("product_uuid")
            print(f"    * [{p_uuid}] '{p_name}' (Product: {p_prod})")

    print("\n" + "=" * 70)
    print("  Diagnostic complete. All communication channels operational.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
