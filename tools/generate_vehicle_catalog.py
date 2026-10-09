"""
Generates / refreshes local/lmu_vehicle_catalog.json from LMU's own REST API
(GET http://127.0.0.1:6397/rest/sessions/getAllVehicles). LMU must be running.

The daemon already does this automatically whenever LMU starts or an unknown car is loaded;
this tool is for doing it by hand and seeing what was added.

Existing catalog entries are kept (they may come from a more precise source such as
LMUTrackPipeline); only vehicle IDs that are not in the catalog yet are added.

Usage:
    python tools/generate_vehicle_catalog.py [--out PATH] [--raw raw_response.json] [--dry-run]
"""

import os
import sys
import json
import argparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from simagic_daemon.lmu_reader import fetch_json
from simagic_daemon import catalog_sync as cs
from simagic_daemon import vehicle_mapping as vm


def main():
    default_out = cs.catalog_path()
    parser = argparse.ArgumentParser(description="Build the vehicle catalog from LMU's REST API")
    parser.add_argument("--out", default=default_out, help=f"Catalog to update (default: {default_out})")
    parser.add_argument("--raw", help="Also save the raw getAllVehicles response to this file")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be added without writing")
    args = parser.parse_args()

    data = fetch_json(cs.ALL_VEHICLES_URL, timeout=cs.ALL_VEHICLES_TIMEOUT)
    if data is None:
        sys.exit(f"LMU REST API not reachable ({cs.ALL_VEHICLES_URL}). Start LMU and try again.")
    if args.raw:
        with open(args.raw, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        print(f"Raw response saved to {args.raw}")

    rows = cs.vehicle_rows(data)
    if not rows:
        sys.exit("getAllVehicles returned no vehicle rows; save it with --raw and check the response shape.")
    print(f"LMU reports {len(rows)} vehicles. Fields of the first one: {sorted(rows[0].keys())}")

    catalog = cs.load_catalog_file(args.out)
    added = cs.merge_rows(catalog, rows)
    total_added = sum(len(ids) for ids in added.values())
    print(f"New vehicle IDs: {total_added}")
    for (model, car_class), ids in sorted(added.items()):
        rule = vm.match_vehicle(model, car_class, use_catalog=False).rule
        status = f"-> {rule.model_name} [{rule.preset_key}]" if rule else "-> NO RULE (class default profile)"
        print(f"  + {model} [{car_class}]: {len(ids)} ID(s) {status}")

    if args.dry_run or not total_added:
        print("Nothing written." if not total_added else "Dry run: nothing written.")
        return
    cs.save_catalog_file(args.out, catalog)
    print(f"Catalog written: {args.out}")


if __name__ == "__main__":
    main()
