"""
Diagnostic Tool: Test Le Mans Ultimate (LMU) Telemetry & REST API Connection
Inspects LMU's embedded HTTP server (port 6397), rFactor 2 shared memory ($rFactor2SMMP_Scoring$),
and validates vehicle resolution against the daemon's vehicle mapping table.
"""

import sys
import os
import json

# Safe UTF-8 encoding on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add src to python path for imports if run directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from simagic_daemon.lmu_reader import LMUReader
from simagic_daemon.vehicle_mapping import resolve_vehicle_to_preset


def main():
    print("=" * 70)
    print("      LE MANS ULTIMATE (LMU) CONNECTION & VEHICLE DIAGNOSTIC      ")
    print("=" * 70)

    reader = LMUReader()

    # 1. Check LMU REST API
    print("\n[1] Checking LMU embedded REST server (http://localhost:6397)...")
    rest_online = reader.is_rest_api_online()
    if rest_online:
        print("  [OK] LMU REST API is ONLINE!")
        rest_veh = reader.get_rest_vehicle()
        if rest_veh:
            print("  Active vehicle data from REST:")
            for k, v in rest_veh.items():
                print(f"    * {k}: {v}")
        else:
            print("  [INFO] Connected to REST API, but no vehicle is currently loaded.")
    else:
        print("  [--] LMU REST API is offline (game not running or not listening on port 6397).")

    # 2. Check Shared Memory
    print("\n[2] Checking rFactor 2 Shared Memory ($rFactor2SMMP_Scoring$)...")
    sm_online = reader.connect_shared_memory()
    if sm_online:
        print("  [OK] Shared memory buffer successfully mapped!")
        sm_veh = reader.get_shared_memory_vehicle()
        if sm_veh:
            print("  Active session data from Shared Memory:")
            for k, v in sm_veh.items():
                print(f"    * {k}: {v}")
        else:
            print("  [INFO] Shared memory mapped, but simulation is not currently in a track session.")
    else:
        print("  [--] Shared memory buffer not found (LMU is not running).")

    # 3. Overall Detection Status
    print("\n[3] Unified Vehicle Detection Engine Status:")
    active_car = reader.get_active_vehicle()
    if active_car:
        ident = active_car.get("identifier", "")
        print(f"  [FOUND] Active Vehicle Identifier: '{ident}'")
        model, uuid, preset_name = resolve_vehicle_to_preset(ident)
        print(f"  -> Model Name       : {model}")
        print(f"  -> Target GT NEO    : '{preset_name}' (UUID: {uuid})")
    else:
        print("  [IDLE] No active LMU car currently detected.")
        print("  When you launch LMU and select a car/track, the daemon will auto-detect it here.")

    # 4. Vehicle Mapping Verification Test Suite
    print("\n[4] Vehicle Mapping Table Verification (Simulated LMU Car Grid):")
    sample_cars = [
        ("Ferrari 296 GT3", "296_GT3.veh"),
        ("McLaren 720S LMGT3", "720s_gt3.veh"),
        ("Porsche 911 GT3 R", "911_gt3_r.veh"),
        ("BMW M4 GT3", "bmw_m4_gt3.veh"),
        ("Ford Mustang GT3", "mustang_gt3.veh"),
        ("Corvette Z06 GT3.R", "corvette_z06.veh"),
        ("Lexus RC F GT3", "lexus_rcf_gt3.veh"),
        ("Aston Martin Vantage GTE", "amr_gte_dstati.veh"),
        ("Cadillac V-Series.R Hypercar", "cadillac_v-series.r.veh"),
        ("Peugeot 9X8 Hypercar", "peugeot_9x8.veh"),
        ("Aston Martin Valkyrie LMH", "valkyrie_lmh.veh"),
        ("Oreca 07 LMP2", "oreca_07_lmp2.veh"),
        ("Ginetta G61-LT-P325 LMP3", "ginetta_g61.veh"),
    ]

    for label, veh_id in sample_cars:
        model, uuid, preset_name = resolve_vehicle_to_preset(veh_id)
        print(f"  * {label:<30} -> [{preset_name:<16}] ({uuid})")

    print("\n" + "=" * 70)
    print("  LMU Diagnostic complete.")
    print("=" * 70)
    reader.close_shared_memory()
    return 0


if __name__ == "__main__":
    sys.exit(main())
