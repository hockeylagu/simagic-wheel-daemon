"""
LMU Vehicle Mapping Engine
Resolves Le Mans Ultimate vehicle identifiers (vehFile, carType, manufacturer, model)
to Simagic hardware preset UUIDs for:
1. GT NEO Steering Wheel (Button mappings, clutch bite, LEDs, rev lights)
2. Alpha EVO Sport Wheelbase (FFB profile)
3. Simagic P700 Pedals (Pedal curve)

Resolution strategy:
0. If the exact vehicle ID (the .veh file name) is in the private vehicle catalog
   (local/lmu_vehicle_catalog.json), its known model and class are used.
1. If LMU reports the vehicle class (Hypercar / LMP2 / LMP3 / LMGT3 / GTE), only rules
   of that class are considered, so team names shared across classes (Proton, Iron Lynx,
   WRT...) can never pull a hypercar onto a GT3 profile.
2. Model tokens (e.g. "963", "SC63") are always tried before team tokens (e.g. "PROT").
3. Every car has its own preset key (e.g. "HYP_499P"). If that key is not configured in
   user_presets.json, it falls back along PRESET_FALLBACKS until a configured preset is
   found, ending at "DEFAULT".
"""

from typing import Tuple, Dict, Optional, List, Union, Sequence, NamedTuple

import os
import re
import json
import logging

from .config import load_config, find_local_file

logger = logging.getLogger("simagic_daemon.mapping")

_config = load_config()

# Default template preset mapping
DEFAULT_BASE_PRESET_UUID = str(_config.get("base_preset_uuid", "") or "")
DEFAULT_PEDAL_PRESET_UUID = str(_config.get("pedal_preset_uuid", "") or "")

PRESET_MAP_GT_NEO: Dict[str, str] = {
    # GT3 / LMGT3
    "GT3_296":      "",
    "GT3_720S":     "",
    "GT3_911":      "",
    "GT3_M4":       "",
    "GT3_MUSTANG":  "",
    "GT3_RCF":      "",
    "GT3_VETTE":    "",
    "GT3_HURACAN":  "",
    "GT3_AMG":      "",
    "GT3_VANTAGE":  "",
    "GT3_DEFAULT":  "",

    # GTE
    "GTE_AMR":      "",
    "GTE_RSR":      "",
    "GTE_488":      "",
    "GTE_C8R":      "",

    # Hypercar / LMH / LMDh
    "HYP_CADILLAC": "",
    "HYP_PEUGEOT":  "",
    "HYP_VALKYRIE": "",
    "HYP_499P":     "",
    "HYP_963":      "",
    "HYP_TOYOTA":   "",
    "HYP_ALPINE":   "",
    "HYP_SC63":     "",
    "HYP_BMW":      "",
    "HYP_GENESIS":  "",
    "HYP_ISOTTA":   "",
    "HYP_GLICKENHAUS": "",
    "HYP_VANWALL":  "",
    "HYP_DEFAULT":  "",

    # LMP2 & LMP3
    "LM_P2":         "",
    "WEC_P2":        "",
    "LMP3_GINETTA":  "",
    "LMP3_LIGIER":   "",
    "LMP3_DUQUEINE": "",
    "LMP3_ADESS":    "",

    # Default fallback
    "DEFAULT":      "",
}

# Load user preset UUIDs from the private configuration (see config.py)
for _k, _v in (_config.get("presets") or {}).items():
    PRESET_MAP_GT_NEO[_k] = str(_v) if _v not in (None, "") else ""

# When a preset key has no UUID configured, try its fallback instead (chains end at DEFAULT).
# These reproduce the historical profile sharing, so existing configs keep working unchanged.
PRESET_FALLBACKS: Dict[str, str] = {
    "GT3_HURACAN":   "GT3_296",
    "GT3_AMG":       "GT3_M4",
    "GT3_VANTAGE":   "GTE_AMR",
    "GTE_RSR":       "GTE_AMR",
    "GTE_488":       "GTE_AMR",
    "GTE_C8R":       "GTE_AMR",
    "HYP_499P":      "HYP_CADILLAC",
    "HYP_963":       "HYP_CADILLAC",
    "HYP_TOYOTA":    "HYP_CADILLAC",
    "HYP_ALPINE":    "HYP_CADILLAC",
    "HYP_SC63":      "HYP_CADILLAC",
    "HYP_BMW":       "HYP_CADILLAC",
    "HYP_GENESIS":   "HYP_CADILLAC",
    "HYP_ISOTTA":    "HYP_CADILLAC",
    "HYP_GLICKENHAUS": "HYP_CADILLAC",
    "HYP_VANWALL":   "HYP_CADILLAC",
    "HYP_DEFAULT":   "HYP_CADILLAC",
    "LMP3_LIGIER":   "LMP3_GINETTA",
    "LMP3_DUQUEINE": "LMP3_GINETTA",
    "LMP3_ADESS":    "LMP3_GINETTA",
}

# Human readable profile names shown in logs, tray menu and notifications
PRESET_LABELS: Dict[str, str] = {
    "GT3_296": "GT3 296", "GT3_720S": "GT3 720S", "GT3_911": "GT3 911", "GT3_M4": "GT3 M4",
    "GT3_MUSTANG": "GT3 Mustang", "GT3_RCF": "GT3 RCF", "GT3_VETTE": "GT3 Vette",
    "GT3_HURACAN": "GT3 Huracan", "GT3_AMG": "GT3 AMG", "GT3_VANTAGE": "GT3 Vantage",
    "GT3_DEFAULT": "GT3 Default",
    "GTE_AMR": "GTE AMR", "GTE_RSR": "GTE RSR", "GTE_488": "GTE 488", "GTE_C8R": "GTE C8.R",
    "HYP_CADILLAC": "HYP Cadillac", "HYP_PEUGEOT": "HYP Peugeot", "HYP_VALKYRIE": "HYP Valkyrie",
    "HYP_499P": "HYP 499P", "HYP_963": "HYP 963", "HYP_TOYOTA": "HYP Toyota",
    "HYP_ALPINE": "HYP Alpine", "HYP_SC63": "HYP SC63", "HYP_BMW": "HYP BMW",
    "HYP_GENESIS": "HYP Genesis", "HYP_ISOTTA": "HYP Isotta",
    "HYP_GLICKENHAUS": "HYP Glickenhaus", "HYP_VANWALL": "HYP Vanwall", "HYP_DEFAULT": "HYP Default",
    "LM_P2": "LM P2", "WEC_P2": "WEC P2",
    "LMP3_GINETTA": "LMP3 Ginetta", "LMP3_LIGIER": "LMP3 Ligier", "LMP3_DUQUEINE": "LMP3 Duqueine",
    "LMP3_ADESS": "LMP3 ADESS",
    "DEFAULT": "My GT Neo Default",
}

# Vehicle class categories
CAT_GTE = "GTE"
CAT_GT3 = "GT3"
CAT_HYP = "HYP"
CAT_LMP2 = "LMP2"
CAT_LMP3 = "LMP3"

# Preset key used when the class is known but the exact car is not recognised
CATEGORY_DEFAULT_KEYS: Dict[str, str] = {
    CAT_GTE: "GTE_AMR",
    CAT_GT3: "GT3_DEFAULT",
    CAT_HYP: "HYP_DEFAULT",
    CAT_LMP2: "LM_P2",
    CAT_LMP3: "LMP3_GINETTA",
}

# A token is either a single substring or a tuple of substrings that must all be present.
Token = Union[str, Tuple[str, ...]]


class VehicleRule(NamedTuple):
    category: str
    model_name: str
    preset_key: str
    model_tokens: Tuple[Token, ...]
    team_tokens: Tuple[Token, ...] = ()
    exclude_tokens: Tuple[str, ...] = ()  # the rule never matches if any of these is present
    manufacturers: Tuple[str, ...] = ()   # LMU "manufacturer" values; only used when the class is known


# Order matters within each pass: GTE is checked before GT3 to avoid 911/488 collisions.
VEHICLE_RULES: Tuple[VehicleRule, ...] = (
    # --- GTE ---
    VehicleRule(CAT_GTE, "Aston Martin Vantage GTE", "GTE_AMR",
                ("DSTATI", ("AMR", "GTE"), ("VANTAGE", "AMR")), exclude_tokens=("GT3",), manufacturers=("ASTON",)),
    VehicleRule(CAT_GTE, "Porsche 911 RSR-19 (GTE)", "GTE_RSR", ("RSR", ("911", "GTE")), ("REXY",), manufacturers=("PORSCHE",)),
    VehicleRule(CAT_GTE, "Ferrari 488 GTE EVO", "GTE_488", ("488",), ("KESSEL",), manufacturers=("FERRARI",)),
    VehicleRule(CAT_GTE, "Corvette C8.R GTE", "GTE_C8R", ("C8.R", "C8R"), manufacturers=("CORVETTE", "CHEVROLET")),

    # --- GT3 / LMGT3 ---
    VehicleRule(CAT_GT3, "Ferrari 296 GT3", "GT3_296", ("296",), ("AFCO",), manufacturers=("FERRARI",)),
    VehicleRule(CAT_GT3, "McLaren 720S GT3 Evo", "GT3_720S", ("720S", "MCLAREN"), ("GARA", "GCHAL"), manufacturers=("MCLAREN",)),
    VehicleRule(CAT_GT3, "Porsche 911 GT3 R", "GT3_911", ("911", ("PORSCHE", "GT3")), ("MANT",), manufacturers=("PORSCHE",)),
    VehicleRule(CAT_GT3, "BMW M4 GT3", "GT3_M4", ("M4", ("BMW", "GT3")), ("WRT",), manufacturers=("BMW",)),
    VehicleRule(CAT_GT3, "Ford Mustang GT3", "GT3_MUSTANG", ("MUSTANG", "FORD"), ("PROT",), manufacturers=("FORD",)),
    VehicleRule(CAT_GT3, "Lexus RC F GT3", "GT3_RCF", ("LEXUS", "RCF"), ("AKKO",), manufacturers=("LEXUS",)),
    VehicleRule(CAT_GT3, "Corvette Z06 GT3.R", "GT3_VETTE", ("CORVETTE", "Z06", "VETTE"), ("TFSP",), manufacturers=("CORVETTE", "CHEVROLET")),
    VehicleRule(CAT_GT3, "Lamborghini Huracan GT3 Evo2", "GT3_HURACAN",
                ("HURACAN", ("LAMBORGHINI", "GT3")), ("IRON",), manufacturers=("LAMBORGHINI",)),
    VehicleRule(CAT_GT3, "Mercedes-AMG GT3", "GT3_AMG", ("AMG", "MERCEDES"), manufacturers=("MERCEDES",)),
    VehicleRule(CAT_GT3, "Aston Martin Vantage GT3", "GT3_VANTAGE", ("VANTAGE",), ("THOR",), manufacturers=("ASTON",)),

    # --- Hypercar / LMH / LMDh ---
    VehicleRule(CAT_HYP, "Cadillac V-Series.R", "HYP_CADILLAC",
                ("CADILLAC", "CADIL", "V-SERIES", "VLMDH"), ("WTR",), manufacturers=("CADILLAC",)),
    VehicleRule(CAT_HYP, "Peugeot 9X8", "HYP_PEUGEOT", ("PEUGEOT", "PEUG", "9X8"), manufacturers=("PEUGEOT",)),
    VehicleRule(CAT_HYP, "Aston Martin Valkyrie LMH", "HYP_VALKYRIE", ("VALKYRIE", "007_"), ("THO7",), manufacturers=("ASTON",)),
    VehicleRule(CAT_HYP, "Ferrari 499P", "HYP_499P", ("499P", ("FERRARI", "HYP")), manufacturers=("FERRARI",)),
    VehicleRule(CAT_HYP, "Porsche 963", "HYP_963", ("963",), manufacturers=("PORSCHE",)),
    VehicleRule(CAT_HYP, "Toyota GR010 Hybrid", "HYP_TOYOTA", ("TOYOTA", "TOYOT", "GR010", "TR010"), manufacturers=("TOYOTA",)),
    VehicleRule(CAT_HYP, "Alpine A424", "HYP_ALPINE", ("ALPINE", "A424", "ALPI"), manufacturers=("ALPINE",)),
    VehicleRule(CAT_HYP, "Lamborghini SC63", "HYP_SC63", ("SC63",), manufacturers=("LAMBORGHINI",)),
    VehicleRule(CAT_HYP, "BMW M Hybrid V8", "HYP_BMW", (("BMW", "HYBRID"), "BMWMH", "M_HYBRID", "BMW_HY"), manufacturers=("BMW",)),
    VehicleRule(CAT_HYP, "Genesis GMR001 Hypercar", "HYP_GENESIS", ("GMR001", "GMR-001", "GENESIS", "GENE"), manufacturers=("GENESIS",)),
    VehicleRule(CAT_HYP, "Isotta Fraschini Tipo 6", "HYP_ISOTTA", ("ISOTTA",), manufacturers=("ISOTTA",)),
    VehicleRule(CAT_HYP, "Glickenhaus SCG 007", "HYP_GLICKENHAUS", ("GLICK", "SCG007", "SCG 007"), manufacturers=("GLICKENHAUS",)),
    VehicleRule(CAT_HYP, "Vanwall Vandervell 680", "HYP_VANWALL", ("VANWALL", "VANDERVELL"), manufacturers=("VANWALL",)),

    # --- LMP2 ---
    VehicleRule(CAT_LMP2, "Oreca 07 LMP2", "LM_P2", ("ORECA", "07_LMP2", "LMP2"), ("VECTOR",), manufacturers=("ORECA",)),

    # --- LMP3 ---
    VehicleRule(CAT_LMP3, "Ginetta G61-LT-P325 Evo", "LMP3_GINETTA", ("GINETTA", "G61"), manufacturers=("GINETTA",)),
    VehicleRule(CAT_LMP3, "Ligier JS P325", "LMP3_LIGIER", ("LIGIER", "JSP"), manufacturers=("LIGIER",)),
    VehicleRule(CAT_LMP3, "Duqueine D09", "LMP3_DUQUEINE", ("DUQUEINE", "D09", "D08"), manufacturers=("DUQUEINE",)),
    VehicleRule(CAT_LMP3, "ADESS AD25 LMP3", "LMP3_ADESS", ("ADESS", "AD25", "_ADES"), manufacturers=("ADESS",)),
)


# -----------------------------------------------------------------------------
# Private vehicle catalog: exact vehicle ID (.veh file name) -> model & class
# -----------------------------------------------------------------------------
VEHICLE_CATALOG_FILENAME = "lmu_vehicle_catalog.json"
VEHICLE_CATALOG_ENV_VAR = "SIMAGIC_VEHICLE_CATALOG"


class CatalogEntry(NamedTuple):
    model: str
    car_class: str


def normalize_vehicle_id(identifier: str) -> str:
    """'C:\\...\\Vehicles\\31_24_WRT_6CBE4475.VEH' -> '31_24_WRT_6CBE4475'."""
    base = re.split(r"[\\/]", identifier.strip())[-1]
    return re.sub(r"\.veh$", "", base, flags=re.IGNORECASE).upper()


def load_vehicle_catalog(path: Optional[str] = None) -> Dict[str, CatalogEntry]:
    """
    Loads {"vehicles": [{"model", "carClass", "vehicleIds": [...]}, ...]} (LMULapTime /
    LMUTrackPipeline format, or the output of tools/generate_vehicle_catalog.py).
    Returns {} if no catalog is found or it is invalid.
    """
    path = path or find_local_file(VEHICLE_CATALOG_FILENAME, VEHICLE_CATALOG_ENV_VAR)
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        catalog: Dict[str, CatalogEntry] = {}
        for record in data.get("vehicles", []):
            entry = CatalogEntry(str(record["model"]), str(record.get("carClass", "")))
            for vehicle_id in record.get("vehicleIds", []):
                catalog[normalize_vehicle_id(str(vehicle_id))] = entry
        logger.debug(f"[Mapping] Loaded {len(catalog)} vehicle IDs from {path}")
        return catalog
    except Exception as e:
        logger.warning(f"[Mapping] Ignoring invalid vehicle catalog {path}: {e}")
        return {}


VEHICLE_CATALOG: Dict[str, CatalogEntry] = load_vehicle_catalog()


def reload_vehicle_catalog() -> int:
    """Re-reads the catalog file (after the daemon refreshed it from LMU). Returns the ID count."""
    global VEHICLE_CATALOG
    VEHICLE_CATALOG = load_vehicle_catalog()
    return len(VEHICLE_CATALOG)


def normalize_vehicle_class(vehicle_class: Optional[Union[str, Sequence[str]]]) -> Optional[str]:
    """
    Maps LMU class strings (e.g. "Hypercar", "LMGT3", "LMP2_ELMS", or a list of them)
    to one of the category constants. Returns None if the class is unknown or missing.
    """
    if not vehicle_class:
        return None
    values: List[str] = [vehicle_class] if isinstance(vehicle_class, str) else [str(c) for c in vehicle_class]

    for raw in values:
        c = raw.upper()
        if "HYPER" in c or "LMH" in c or "LMDH" in c:
            return CAT_HYP
        if "LMP3" in c:
            return CAT_LMP3
        if "LMP2" in c:
            return CAT_LMP2
        if "GTE" in c:
            return CAT_GTE
        if "GT3" in c:
            return CAT_GT3
    return None


def _token_matches(token: Token, v: str) -> bool:
    if isinstance(token, tuple):
        return all(part in v for part in token)
    return token in v


def resolve_preset_key(preset_key: str) -> Tuple[str, str]:
    """
    Follows the fallback chain until a preset key with a configured UUID is found.
    Returns (effective preset key, preset UUID). The UUID is "" if nothing is configured,
    not even DEFAULT.
    """
    key = preset_key
    visited = set()
    while key and key not in visited:
        visited.add(key)
        uuid = PRESET_MAP_GT_NEO.get(key, "")
        if uuid:
            if key != preset_key:
                logger.debug(f"[Mapping] Preset '{preset_key}' not configured, using fallback '{key}'")
            return key, uuid
        key = PRESET_FALLBACKS.get(key, "DEFAULT" if key != "DEFAULT" else "")
    logger.warning(f"[Mapping] No preset UUID configured for '{preset_key}' (nor DEFAULT)")
    return "DEFAULT", ""


def get_preset_label(preset_key: str) -> str:
    """Returns the human readable name for a preset key."""
    return PRESET_LABELS.get(preset_key, preset_key.replace("_", " "))


def _result(model_name: str, preset_key: str) -> Tuple[str, str, str]:
    effective_key, uuid = resolve_preset_key(preset_key)
    return (model_name, uuid, get_preset_label(effective_key))


class VehicleMatch(NamedTuple):
    model_name: str
    category: Optional[str]
    rule: Optional[VehicleRule]
    source: str  # "catalog", "tokens", "class-default" or "default"


def _match_rule(v: str, category: Optional[str], manufacturer: str = "") -> Optional[VehicleRule]:
    """
    Token matching on an upper-cased string, restricted to a category when it is known.
    Pass 1: model tokens. Pass 2: manufacturer (only with a known class: a make alone is
    ambiguous across classes). Pass 3: team tokens (teams run cars in several classes).
    """
    rules = [r for r in VEHICLE_RULES
             if (category is None or r.category == category) and not any(x in v for x in r.exclude_tokens)]
    for rule in rules:
        if any(_token_matches(t, v) for t in rule.model_tokens):
            return rule
    make = manufacturer.upper()
    if category is not None and make:
        for rule in rules:
            if any(m in make for m in rule.manufacturers):
                return rule
    for rule in rules:
        if any(_token_matches(t, v) for t in rule.team_tokens):
            return rule
    return None


def match_vehicle(
    vehicle_identifier: str,
    vehicle_class: Optional[Union[str, Sequence[str]]] = None,
    use_catalog: bool = True,
    manufacturer: Optional[str] = None,
) -> VehicleMatch:
    """Identifies the car (rule, category) for a raw LMU vehicle identifier."""
    identifier = (vehicle_identifier or "").strip()
    category = normalize_vehicle_class(vehicle_class)

    if use_catalog and identifier:
        known = VEHICLE_CATALOG.get(normalize_vehicle_id(identifier))
        if known:
            known_category = normalize_vehicle_class(known.car_class) or category
            rule = _match_rule(known.model.upper(), known_category)
            return VehicleMatch(rule.model_name if rule else known.model, known_category, rule, "catalog")

    rule = _match_rule(identifier.upper(), category, manufacturer or "")
    if rule:
        return VehicleMatch(rule.model_name, rule.category, rule, "tokens")
    return VehicleMatch(identifier, category, None, "class-default" if category else "default")


def match_preset_key(match: VehicleMatch) -> str:
    """The preset key a match selects (before falling back to configured presets)."""
    if match.rule:
        return match.rule.preset_key
    # Known class but unknown car: use the class default profile; else the user default
    return CATEGORY_DEFAULT_KEYS[match.category] if match.category is not None else "DEFAULT"


def resolve_vehicle_to_preset(
    vehicle_identifier: str,
    vehicle_class: Optional[Union[str, Sequence[str]]] = None,
    manufacturer: Optional[str] = None,
) -> Tuple[str, str, str]:
    """
    Takes any raw vehicle string (vehFile, carType, model name, or manufacturer) plus the
    optional LMU vehicle class and resolves it to:
    (Friendly Model Name, Target GT NEO Preset UUID, Preset Name)

    The UUID is "" when no preset (not even DEFAULT) is configured; callers must skip switching.
    """
    if not vehicle_identifier or not vehicle_identifier.strip():
        logger.debug("[Mapping] Empty vehicle identifier, returning Default Setup.")
        return _result("Default Setup", "DEFAULT")

    match = match_vehicle(vehicle_identifier, vehicle_class, manufacturer=manufacturer)
    logger.debug(
        f"[Mapping] '{vehicle_identifier}' (class: {vehicle_class!r}) -> {match.model_name} "
        f"[{match.category}] via {match.source}"
    )

    return _result(match.model_name, match_preset_key(match))


if __name__ == "__main__":
    test_cases = [
        ("296_GT3.veh", None),
        ("Ferrari 296 GT3", None),
        ("McLaren 720S LMGT3 Evo", None),
        ("Cadillac V-Series.R", None),
        ("Oreca 07", None),
        ("Peugeot 9x8", None),
        ("Ford Mustang LMGT3", None),
        ("Porsche 911 GT3 R LMGT3", None),
        ("Lexus RCF LMGT3", None),
        ("Aston Martin Valkyrie", None),
        ("Ginetta G61-LT-P325", None),
        ("Porsche 911 RSR", None),
        ("Lamborghini Huracan GT3", None),
        ("Proton Competition Porsche 963", None),
        ("Iron Lynx Lamborghini SC63", None),
        ("WRT_2024", "Hypercar"),
        ("WRT_2024", "LMGT3"),
        ("Unknown_Test_Car", None),
    ]
    print("=" * 70)
    print("       LMU VEHICLE TO SIMAGIC PRESET RESOLUTION VERIFICATION       ")
    print("=" * 70)
    for sample, cls in test_cases:
        model, uuid, preset_name = resolve_vehicle_to_preset(sample, cls)
        label = f"{sample} [{cls}]" if cls else sample
        print(f"  {label:<36} -> {model:<28} | [{preset_name}] ({uuid or 'NOT CONFIGURED'})")
