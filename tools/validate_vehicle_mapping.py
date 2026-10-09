"""
Validates the vehicle mapping against a catalog of real LMU vehicle IDs
(local/lmu_vehicle_catalog.json by default: every installed .veh file with its true model & class).

Every vehicle ID is resolved four ways:
  catalog            exact ID lookup (what the daemon does when the catalog is present)
  id + class + make  rules on the ID with LMU's class and manufacturer (REST nav state, no catalog).
                     The manufacturer is simulated as the first word of the catalog model name.
  id + class         rules on the ID with the class only (standings / shared memory, no catalog)
  id only            rules on the ID alone (worst case)
Two scores per mode: "car" (exact car identified) and "profile" (the preset key that would be
selected is the right one; e.g. an unidentified LMP2 Oreca still gets the LMP2 class profile).

Usage:
    python tools/validate_vehicle_mapping.py [catalog.json] [--show N]
"""

import os
import sys
import argparse
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from simagic_daemon import vehicle_mapping as vm

# Catalog model name -> the daemon's model name for that car (None: no dedicated rule expected)
EXPECTED_MODELS = {
    "Aston Martin Vantage AMR": "Aston Martin Vantage GTE",
    "Corvette C8.R GTE": "Corvette C8.R GTE",
    "Ferrari 488 GTE EVO": "Ferrari 488 GTE EVO",
    "Porsche 911 RSR-19": "Porsche 911 RSR-19 (GTE)",
    "Aston Martin Vantage AMR LMGT3": "Aston Martin Vantage GT3",
    "BMW M4 LMGT3": "BMW M4 GT3",
    "Chevrolet Corvette Z06 LMGT3.R": "Corvette Z06 GT3.R",
    "Ferrari 296 LMGT3": "Ferrari 296 GT3",
    "Ferrari 296 LMGT3 Evo": "Ferrari 296 GT3",
    "Ford Mustang LMGT3": "Ford Mustang GT3",
    "Lamborghini Huracan LMGT3 Evo2": "Lamborghini Huracan GT3 Evo2",
    "Lexus RCF LMGT3": "Lexus RC F GT3",
    "McLaren 720S LMGT3 Evo": "McLaren 720S GT3 Evo",
    "Mercedes-AMG LMGT3": "Mercedes-AMG GT3",
    "Porsche 911 GT3 R LMGT3": "Porsche 911 GT3 R",
    "Alpine A424": "Alpine A424",
    "Aston Martin Valkyrie LMH": "Aston Martin Valkyrie LMH",
    "BMW M Hybrid V8": "BMW M Hybrid V8",
    "Cadillac V-Series.R": "Cadillac V-Series.R",
    "Ferrari 499P": "Ferrari 499P",
    "Genesis GMR-001": "Genesis GMR001 Hypercar",
    "Glickenhaus SCG007": "Glickenhaus SCG 007",
    "Isotta Fraschini TIPO6": "Isotta Fraschini Tipo 6",
    "Lamborghini SC63": "Lamborghini SC63",
    "Peugeot 9x8": "Peugeot 9X8",
    "Porsche 963": "Porsche 963",
    "Toyota GR010": "Toyota GR010 Hybrid",
    "Toyota TR010": "Toyota GR010 Hybrid",
    "Vanwall 680": "Vanwall Vandervell 680",
    "Oreca 07": "Oreca 07 LMP2",
    "ADESS AD25 LMP3": "ADESS AD25 LMP3",
    "Duqueine D09 P3": "Duqueine D09",
    "Ginetta G61-LT-P325 Evo": "Ginetta G61-LT-P325 Evo",
    "Ligier JS P325": "Ligier JS P325",
    "Porsche 992S Pace Car": None,
}

MODES = ("catalog", "id + class + make", "id + class", "id only")
RULE_KEYS = {rule.model_name: rule.preset_key for rule in vm.VEHICLE_RULES}


def main():
    parser = argparse.ArgumentParser(description="Validate the vehicle mapping against real LMU vehicle IDs")
    parser.add_argument("catalog", nargs="?", help="Catalog JSON (default: local/lmu_vehicle_catalog.json)")
    parser.add_argument("--show", type=int, default=5, help="Failing IDs to list per car and mode (default 5)")
    args = parser.parse_args()

    path = args.catalog or vm.find_local_file(vm.VEHICLE_CATALOG_FILENAME, vm.VEHICLE_CATALOG_ENV_VAR)
    if not path:
        sys.exit("No catalog found. Pass a path or create local/lmu_vehicle_catalog.json "
                 "(python tools/generate_vehicle_catalog.py while LMU is running).")
    catalog = vm.load_vehicle_catalog(path)
    vm.VEHICLE_CATALOG = catalog  # validate this catalog, whatever the daemon would load
    print(f"Catalog: {path} ({len(catalog)} vehicle IDs)\n")

    unknown_models = sorted({e.model for e in catalog.values()} - set(EXPECTED_MODELS))
    if unknown_models:
        print("Models missing from EXPECTED_MODELS (add them to this tool):")
        for model in unknown_models:
            print(f"  - {model}")
        print()

    totals = {mode: [0, 0, 0] for mode in MODES}  # car ok, profile ok, total
    failures = {mode: defaultdict(list) for mode in MODES}  # wrong profile only
    for vehicle_id, entry in sorted(catalog.items()):
        if entry.model not in EXPECTED_MODELS:
            continue
        expected_model = EXPECTED_MODELS[entry.model]
        expected_category = vm.normalize_vehicle_class(entry.car_class)
        if expected_model:
            expected_key = RULE_KEYS[expected_model]
        else:
            expected_key = vm.CATEGORY_DEFAULT_KEYS[expected_category] if expected_category else "DEFAULT"
        for mode in MODES:
            match = vm.match_vehicle(
                vehicle_id,
                entry.car_class if "class" in mode else None,
                use_catalog=(mode == "catalog"),
                manufacturer=entry.model.split()[0] if "make" in mode else None,
            )
            got_model = match.rule.model_name if match.rule else None
            got_key = vm.match_preset_key(match)
            totals[mode][2] += 1
            if got_model == expected_model and match.category == expected_category:
                totals[mode][0] += 1
            if got_key == expected_key:
                totals[mode][1] += 1
            else:
                failures[mode][(entry.model, entry.car_class)].append(
                    f"{vehicle_id} -> {got_model or match.model_name} [{got_key}], expected [{expected_key}]")

    print(f"{'mode':<18} {'car':>15} {'profile':>15}")
    for mode in MODES:
        car_ok, profile_ok, total = totals[mode]
        pct = lambda n: f"{n:>4}/{total} {100.0 * n / max(total, 1):5.1f}%"
        print(f"{mode:<18} {pct(car_ok)} {pct(profile_ok)}")
    for mode in MODES:
        if not failures[mode]:
            continue
        print(f"\n--- Wrong profile: {mode} ---")
        for (model, car_class), rows in sorted(failures[mode].items(), key=lambda kv: -len(kv[1])):
            print(f"  {model} [{car_class}]: {len(rows)} ID(s)")
            for row in rows[:args.show]:
                print(f"      {row}")

    sys.exit(0 if totals["catalog"][1] == totals["catalog"][2] else 1)


if __name__ == "__main__":
    main()
