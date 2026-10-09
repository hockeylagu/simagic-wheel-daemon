"""
LMU Raw Data Capture & Replay
Records exactly what LMU exposes (REST documents + rF2 shared memory scoring buffer) so the
reader's field names and struct offsets can be verified, and parsing changes can be tested
offline without launching the game.

Capture layout (one folder per session, inside the gitignored local/ directory by default):
    index.jsonl             one line per saved snapshot: time, source, file, parsed result
    0001_nav_state.json     raw /navigation/state document
    0002_standings.json     raw /rest/watch/standings document
    0003_scoring.bin        raw $rFactor2SMMP_Scoring$ buffer
A snapshot is only written when that source's content changes, to keep captures small.
"""

import os
import json
import time
import hashlib
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Iterator, Tuple

from .lmu_reader import (
    LMUReader,
    fetch_json,
    parse_nav_state,
    parse_standings,
    parse_scoring_buffer,
    LMU_REST_NAV_URL,
    LMU_REST_STANDINGS_URL,
)

logger = logging.getLogger("simagic_daemon.capture")

SOURCES = {
    "nav_state": ".json",
    "standings": ".json",
    "scoring": ".bin",
}


def default_capture_dir() -> str:
    return os.path.join(os.getcwd(), "local", "captures", datetime.now().strftime("%Y%m%d_%H%M%S"))


def parse_capture_file(source: str, path: str) -> Optional[Dict[str, Any]]:
    """Runs a captured file through the same parser the live reader uses."""
    if source == "scoring":
        with open(path, "rb") as f:
            return parse_scoring_buffer(f.read())
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return parse_nav_state(data) if source == "nav_state" else parse_standings(data)


def iter_capture(capture_dir: str) -> Iterator[Tuple[Dict[str, Any], Optional[Dict[str, Any]]]]:
    """Yields (index entry, result of re-parsing the file with the current code) for a capture folder."""
    with open(os.path.join(capture_dir, "index.jsonl"), "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            yield entry, parse_capture_file(entry["source"], os.path.join(capture_dir, entry["file"]))


def run_capture(
    out_dir: Optional[str] = None,
    interval: float = 1.0,
    duration: Optional[float] = None,
    should_stop=lambda: False,
) -> str:
    """
    Polls LMU and saves every change of raw data until Ctrl+C, `duration` seconds,
    or should_stop() returns True. Returns the capture folder.
    """
    out_dir = out_dir or default_capture_dir()
    os.makedirs(out_dir, exist_ok=True)
    reader = LMUReader()
    last_hash: Dict[str, str] = {}
    counter = 0
    started = time.time()

    logger.info(f"[Capture] Recording LMU raw data to {out_dir} (Ctrl+C to stop)")
    try:
        with open(os.path.join(out_dir, "index.jsonl"), "a", encoding="utf-8") as index:
            while not should_stop() and (duration is None or time.time() - started < duration):
                raw: Dict[str, Optional[bytes]] = {}
                nav = fetch_json(LMU_REST_NAV_URL)
                raw["nav_state"] = json.dumps(nav, indent=2).encode("utf-8") if nav is not None else None
                standings = fetch_json(LMU_REST_STANDINGS_URL)
                raw["standings"] = json.dumps(standings, indent=2).encode("utf-8") if standings is not None else None
                raw["scoring"] = reader.read_scoring_raw()

                for source, payload in raw.items():
                    if payload is None:
                        continue
                    digest = hashlib.sha1(payload).hexdigest()
                    if last_hash.get(source) == digest:
                        continue
                    last_hash[source] = digest
                    counter += 1
                    filename = f"{counter:04d}_{source}{SOURCES[source]}"
                    path = os.path.join(out_dir, filename)
                    with open(path, "wb") as f:
                        f.write(payload)
                    try:
                        parsed = parse_capture_file(source, path)
                    except Exception as e:
                        parsed = {"error": str(e)}
                    index.write(json.dumps({
                        "time": datetime.now().isoformat(timespec="milliseconds"),
                        "source": source,
                        "file": filename,
                        "parsed": parsed,
                    }) + "\n")
                    index.flush()
                    logger.info(f"[Capture] {filename} -> {parsed}")

                time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        reader.close_shared_memory()

    logger.info(f"[Capture] Stopped. {counter} snapshot(s) saved in {out_dir}")
    return out_dir
