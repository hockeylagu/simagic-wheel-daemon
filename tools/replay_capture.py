"""
Replays a capture recorded with `simagic-daemon --capture` through the current parsing and
vehicle-mapping code, so reader/mapping changes can be checked without launching LMU.

Usage:
    python tools/replay_capture.py local/captures/<session>
"""

import os
import sys
import argparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from simagic_daemon.capture import iter_capture
from simagic_daemon.vehicle_mapping import resolve_vehicle_to_preset


def main():
    parser = argparse.ArgumentParser(description="Replay an LMU raw data capture through the current code")
    parser.add_argument("capture_dir", help="Capture folder containing index.jsonl")
    args = parser.parse_args()

    changed = 0
    for entry, parsed in iter_capture(args.capture_dir):
        marker = "  "
        if parsed != entry.get("parsed"):
            marker = "≠ "  # parsing result differs from what was recorded at capture time
            changed += 1
        line = f"{marker}{entry['time']}  {entry['file']:<24} "
        if parsed and parsed.get("identifier"):
            cls = parsed.get("classes") or parsed.get("class")
            model, uuid, preset = resolve_vehicle_to_preset(parsed["identifier"], cls, parsed.get("manufacturer"))
            line += f"{parsed['identifier']!r} [{cls or 'n/a'}] -> {model} | [{preset}]"
        else:
            line += f"{parsed}"
        print(line)

    print(f"\n{changed} snapshot(s) parse differently from capture time (marked ≠).")


if __name__ == "__main__":
    main()
