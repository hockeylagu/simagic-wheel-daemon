"""
Vehicle Catalog Sync
Builds / refreshes the private vehicle catalog (lmu_vehicle_catalog.json) from LMU's own REST API
(GET /rest/sessions/getAllVehicles), which lists every installed car and livery with its .veh
file, manufacturer and classes.

Used both by the daemon (automatic refresh, see daemon.py) and tools/generate_vehicle_catalog.py.
Existing catalog entries are never removed or changed; only unknown vehicle IDs are added.
"""

import os
import json
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from .config import find_local_file, candidate_local_paths
from .lmu_reader import fetch_json
from . import vehicle_mapping as vm

logger = logging.getLogger("simagic_daemon.catalog")

ALL_VEHICLES_URL = "http://127.0.0.1:6397/rest/sessions/getAllVehicles"
ALL_VEHICLES_TIMEOUT = 15.0


def catalog_path() -> str:
    """The catalog in use, or where a new one is created (local/ next to the code)."""
    existing = find_local_file(vm.VEHICLE_CATALOG_FILENAME, vm.VEHICLE_CATALOG_ENV_VAR)
    if existing:
        return existing
    candidates = candidate_local_paths(vm.VEHICLE_CATALOG_FILENAME)
    repo_local = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "local", vm.VEHICLE_CATALOG_FILENAME)
    )
    return repo_local if repo_local in candidates else candidates[-1]


def vehicle_rows(data: Any) -> List[Dict[str, Any]]:
    """The endpoint is documented as a list; accept a {"...": [...]} wrapper too."""
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value
    return []


def model_text(row: Dict[str, Any]) -> str:
    """Manufacturer + model, e.g. 'Porsche 963'; the last part of fullPathTree is the car model."""
    tree = str(row.get("fullPathTree") or "")
    model = tree.split(",")[-1].strip() if tree else ""
    model = model or str(row.get("vehicle") or "").strip()
    make = str(row.get("manufacturer") or "").strip()
    if make and not model.upper().startswith(make.upper()):
        model = f"{make} {model}".strip()
    return model


def car_class(row: Dict[str, Any]) -> str:
    """The first LMU class the mapping understands (e.g. 'Hypercar' out of ['Hypercar', 'WEC2025'])."""
    classes = row.get("classes") or []
    classes = [classes] if isinstance(classes, str) else [str(c) for c in classes]
    for cls in classes:
        if vm.normalize_vehicle_class(cls):
            return cls
    return classes[0] if classes else ""


def merge_rows(catalog: Dict[str, Any], rows: List[Dict[str, Any]]) -> Dict[Tuple[str, str], List[str]]:
    """Adds unknown vehicle IDs from getAllVehicles rows to `catalog` in place. Returns what was added."""
    known_ids = {vm.normalize_vehicle_id(i) for v in catalog.get("vehicles", []) for i in v.get("vehicleIds", [])}
    added: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    for row in rows:
        veh_file = str(row.get("vehFile") or "")
        if not veh_file:
            continue
        vehicle_id = vm.normalize_vehicle_id(veh_file)
        if vehicle_id in known_ids:
            continue
        known_ids.add(vehicle_id)
        added[(model_text(row), car_class(row))].append(vehicle_id)

    # Append only: existing records (including several records for one model) are left untouched
    vehicles = catalog.setdefault("vehicles", [])
    first_record = {}
    for record in vehicles:
        first_record.setdefault((record["model"], record.get("carClass", "")), record)
    for (model, cls), ids in sorted(added.items()):
        record = first_record.get((model, cls))
        if record is None:
            record = {"model": model, "carClass": cls, "vehicleIds": []}
            vehicles.append(record)
            first_record[(model, cls)] = record
        record["vehicleIds"].extend(sorted(ids))
    catalog["schemaVersion"] = 1
    catalog.setdefault("source", "LMU REST /rest/sessions/getAllVehicles")
    return dict(added)


def load_catalog_file(path: str) -> Dict[str, Any]:
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"schemaVersion": 1, "vehicles": []}


def save_catalog_file(path: str, catalog: Dict[str, Any]):
    """Writes atomically so a crash or a concurrent reader never sees a half-written file."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=1)
    os.replace(tmp, path)


def refresh_catalog(path: Optional[str] = None, data: Any = None) -> Tuple[int, Optional[str]]:
    """
    Fetches getAllVehicles (unless `data` is given) and adds unknown vehicle IDs to the catalog.
    Returns (number of IDs added, error message or None). Never raises.
    """
    path = path or catalog_path()
    try:
        if data is None:
            data = fetch_json(ALL_VEHICLES_URL, timeout=ALL_VEHICLES_TIMEOUT)
        if data is None:
            return 0, "LMU REST API not reachable"
        rows = vehicle_rows(data)
        if not rows:
            return 0, "getAllVehicles returned no vehicle rows"
        catalog = load_catalog_file(path)
        added = merge_rows(catalog, rows)
        count = sum(len(ids) for ids in added.values())
        if count:
            save_catalog_file(path, catalog)
            for (model, cls), ids in sorted(added.items()):
                logger.info(f"[Catalog] + {model} [{cls}]: {len(ids)} vehicle ID(s)")
            logger.info(f"[Catalog] Added {count} vehicle ID(s) from LMU to {path}")
        else:
            logger.debug(f"[Catalog] Up to date ({len(rows)} vehicles reported by LMU)")
        return count, None
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"
