"""
Generates local/user_presets.json from SimPro Manager's local database
(%LOCALAPPDATA%\\Simagic\\Simpro3\\storage\\user.db). Works offline: SimPro and the wheel do not
need to be running.

What it fills in:
  * base / wheel / pedal product & device UUIDs (from the profiles SimPro stored for each device)
  * base_preset_uuid: your LMU wheelbase profile (tagged "lmu" in SimPro, "My ..." preferred)
  * presets: each GT NEO profile key (GT3_296, HYP_CADILLAC, ...) matched to the SimPro wheel
    profile of the same name ("GT3 296", "HYP Cadillac", ...) or, failing that, whose name
    contains the car (e.g. "Porsche 963" -> HYP_963). Only profiles tagged "lmu" are used,
    plus a "Default" one for DEFAULT.

Existing values in the output file are kept unless --overwrite is given; unmatched keys stay
empty and fall back to related profiles (see PRESET_FALLBACKS in vehicle_mapping.py).

Usage:
    python tools/setup_user_presets.py [--out PATH] [--wheel-product 33947648] [--overwrite] [--dry-run]
"""

import os
import sys
import json
import sqlite3
import argparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from simagic_daemon.config import find_config_path, CONFIG_FILENAME
from simagic_daemon.simagic_client import USER_DB_PATH
from simagic_daemon import vehicle_mapping as vm

BASE_PRODUCT_UUID = "17301504"    # Alpha EVO family wheelbase
WHEEL_PRODUCT_UUID = "33947648"   # GT NEO
PEDAL_PRODUCT_UUID = "50724864"   # P700


def read_presets(db_path: str):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT presetName, presetUUID, productUUID, deviceUUID, gameList FROM preset ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    presets = []
    for name, uuid, product, device, games in rows:
        try:
            game_list = [str(g).lower() for g in json.loads(games)] if games else []
        except ValueError:
            game_list = []
        presets.append({"name": str(name), "uuid": str(uuid), "product": str(product),
                        "device": str(device), "games": game_list})
    return presets


def device_uuid(presets, product: str) -> str:
    devices = {p["device"] for p in presets if p["product"] == product and p["device"]}
    if len(devices) > 1:
        print(f"  ! Several device UUIDs stored for product {product}; using the most recent one.")
    for p in reversed(presets):
        if p["product"] == product and p["device"]:
            return p["device"]
    return ""


def pick_base_preset(presets) -> dict:
    lmu = [p for p in presets if p["product"] == BASE_PRODUCT_UUID and "lmu" in p["games"]]
    mine = [p for p in lmu if p["name"].lower().startswith("my ")]
    return (mine or lmu or [{}])[0]


def match_wheel_presets(presets, wheel_product: str):
    """Returns {preset key: (preset name, uuid)} for the wheel profiles."""
    wheel = [p for p in presets if p["product"] == wheel_product]
    lmu = [p for p in wheel if "lmu" in p["games"]]
    label_to_key = {label.upper(): key for key, label in vm.PRESET_LABELS.items()}
    key_names = {key.upper(): key for key in vm.PRESET_MAP_GT_NEO}
    matches = {}

    # 1. Exact name: "GT3 296" (label) or "GT3_296" (key)
    for p in lmu:
        name = p["name"].strip().upper()
        key = label_to_key.get(name) or key_names.get(name.replace(" ", "_"))
        if key and key != "DEFAULT" and key not in matches:
            matches[key] = (p["name"], p["uuid"])

    # 2. Car named in the profile ("Porsche 963 Hypercar" -> HYP_963)
    for p in lmu:
        if any(p["uuid"] == uuid for _, uuid in matches.values()):
            continue
        rule = vm.match_vehicle(p["name"], use_catalog=False).rule
        if rule and rule.preset_key not in matches:
            matches[rule.preset_key] = (p["name"], p["uuid"])

    # 3. DEFAULT: a wheel profile named "...Default", user-made ("My ...") first
    defaults = [p for p in wheel if "default" in p["name"].lower()]
    defaults.sort(key=lambda p: not p["name"].lower().startswith("my "))
    if defaults:
        matches["DEFAULT"] = (defaults[0]["name"], defaults[0]["uuid"])
    return matches, [p for p in lmu if not any(p["uuid"] == u for _, u in matches.values())]


def main():
    default_out = find_config_path() or os.path.join(os.getcwd(), "local", CONFIG_FILENAME)
    parser = argparse.ArgumentParser(description="Generate user_presets.json from SimPro's database")
    parser.add_argument("--out", default=default_out, help=f"Output file (default: {default_out})")
    parser.add_argument("--db", default=USER_DB_PATH, help="SimPro user.db path")
    parser.add_argument("--wheel-product", default=WHEEL_PRODUCT_UUID, help="Wheel product UUID (default: GT NEO)")
    parser.add_argument("--overwrite", action="store_true", help="Replace values already in the output file")
    parser.add_argument("--dry-run", action="store_true", help="Show the result without writing")
    args = parser.parse_args()

    if not os.path.isfile(args.db):
        sys.exit(f"SimPro database not found: {args.db}\nInstall SimPro Manager v3 and create your profiles first.")
    presets = read_presets(args.db)

    generated = {
        "base_product_uuid": BASE_PRODUCT_UUID,
        "base_device_uuid": device_uuid(presets, BASE_PRODUCT_UUID),
        "base_preset_uuid": pick_base_preset(presets).get("uuid", ""),
        "wheel_product_uuid": args.wheel_product,
        "wheel_device_uuid": device_uuid(presets, args.wheel_product),
        "pedal_product_uuid": PEDAL_PRODUCT_UUID,
        "pedal_device_uuid": device_uuid(presets, PEDAL_PRODUCT_UUID),
    }
    matches, unmatched = match_wheel_presets(presets, args.wheel_product)
    generated["presets"] = {key: uuid for key, (_, uuid) in matches.items()}

    existing = {}
    if os.path.isfile(args.out):
        with open(args.out, "r", encoding="utf-8") as f:
            existing = json.load(f)
    result = dict(existing)
    kept = 0
    for key, value in generated.items():
        if key == "presets":
            continue
        if value and (args.overwrite or not existing.get(key)):
            result[key] = value
        elif existing.get(key) and existing.get(key) != value:
            kept += 1
    presets_out = dict(existing.get("presets", {}))
    for key in vm.PRESET_MAP_GT_NEO:
        new = generated["presets"].get(key, "")
        if new and (args.overwrite or not presets_out.get(key)):
            presets_out[key] = new
        elif presets_out.get(key) and new and presets_out[key] != new:
            kept += 1
        presets_out.setdefault(key, "")
    result["presets"] = presets_out

    base = pick_base_preset(presets)
    print(f"SimPro database: {args.db}")
    print(f"  Wheelbase device : {'found' if generated['base_device_uuid'] else 'NOT FOUND'}")
    print(f"  Wheel device     : {'found' if generated['wheel_device_uuid'] else 'NOT FOUND'}")
    print(f"  Base LMU profile : {base.get('name', 'NOT FOUND (tag a wheelbase profile with LMU in SimPro)')}")
    print("\n  GT NEO profile keys:")
    for key in vm.PRESET_MAP_GT_NEO:
        uuid = presets_out.get(key, "")
        if key in matches and matches[key][1] == uuid:
            source = f"'{matches[key][0]}'"
        elif uuid:
            source = "(kept from existing file)"
        else:
            fallback = vm.PRESET_FALLBACKS.get(key, "DEFAULT")
            source = "-- NOT SET (no profile switch possible)" if key == "DEFAULT" else f"-- not set, falls back to {fallback}"
        print(f"    {key:<16} {source}")
    if unmatched:
        print("\n  LMU-tagged wheel profiles not matched to any key (rename them or set them by hand):")
        for p in unmatched:
            print(f"    - '{p['name']}'")
    if kept:
        print(f"\n  {kept} existing value(s) differ from SimPro and were kept (use --overwrite to replace).")

    if args.dry_run:
        print("\nDry run: nothing written.")
        return
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"\nWritten: {args.out}")


if __name__ == "__main__":
    main()
