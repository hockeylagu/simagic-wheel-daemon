"""
LMU Vehicle Mapping Engine
Resolves Le Mans Ultimate vehicle identifiers (vehFile, carType, manufacturer, model)
to Simagic hardware preset UUIDs for:
1. GT NEO Steering Wheel (Button mappings, clutch bite, LEDs, rev lights)
2. Alpha EVO Sport Wheelbase (FFB profile: 'My LeMans Ultimate')
3. Simagic P700 Pedals (Pedal curve: 'My Default Linear')
"""

from typing import Tuple, Dict, Any, Optional

import os
import json
import logging

logger = logging.getLogger("simagic_daemon.mapping")

# Default template preset mapping
DEFAULT_BASE_PRESET_UUID = ""
DEFAULT_PEDAL_PRESET_UUID = ""

PRESET_MAP_GT_NEO = {
    # GT3 / LMGT3
    "GT3_296":     "",
    "GT3_720S":    "",
    "GT3_911":     "",
    "GT3_M4":      "",
    "GT3_MUSTANG": "",
    "GT3_RCF":     "",
    "GT3_VETTE":   "",

    # GTE
    "GTE_AMR":     "",

    # Hypercar / LMH / LMDh
    "HYP_CADILLAC": "",
    "HYP_PEUGEOT":  "",
    "HYP_VALKYRIE": "",

    # LMP2 & LMP3
    "LM_P2":        "",
    "WEC_P2":       "",
    "LMP3_GINETTA": "",

    # Default fallback
    "DEFAULT":      "",
}

# Dynamically load from gitignored local configuration if present
_LOCAL_PRESETS_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "local", "user_presets.json")
)
if os.path.exists(_LOCAL_PRESETS_PATH):
    try:
        with open(_LOCAL_PRESETS_PATH, "r", encoding="utf-8") as _f:
            _data = json.load(_f)
            DEFAULT_BASE_PRESET_UUID = str(_data.get("base_preset_uuid", ""))
            DEFAULT_PEDAL_PRESET_UUID = str(_data.get("pedal_preset_uuid", ""))
            if "presets" in _data:
                for _k, _v in _data["presets"].items():
                    PRESET_MAP_GT_NEO[_k] = str(_v)
    except Exception as _e:
        logger.warning(f"Failed to load local presets: {_e}")


logger = logging.getLogger("simagic_daemon.mapping")


def resolve_vehicle_to_preset(vehicle_identifier: str) -> Tuple[str, str, str]:
    """
    Takes any raw vehicle string (vehFile, carType, model name, or manufacturer)
    and resolves it to:
    (Friendly Model Name, Target GT NEO Preset UUID, Preset Name)
    """
    if not vehicle_identifier or not vehicle_identifier.strip():
        logger.debug("[Mapping] Empty vehicle identifier, returning Default Setup.")
        return ("Default Setup", PRESET_MAP_GT_NEO["DEFAULT"], "My GT Neo Default")

    v = vehicle_identifier.upper()
    logger.debug(f"[Mapping] Resolving vehicle token: '{vehicle_identifier}' (normalized: '{v}')")

    # --- GTE (Check first to avoid generic GT3 collisions on 911/488) ---
    if "DSTATI" in v or ("AMR" in v and "GTE" in v):
        return ("Aston Martin Vantage GTE", PRESET_MAP_GT_NEO["GTE_AMR"], "GTE AMR")
    if "RSR" in v or "REXY" in v:
        return ("Porsche 911 RSR-19 (GTE)", PRESET_MAP_GT_NEO["GTE_AMR"], "GTE AMR")
    if "488" in v or "KESSEL" in v:
        return ("Ferrari 488 GTE EVO", PRESET_MAP_GT_NEO["GTE_AMR"], "GTE AMR")

    # --- GT3 / LMGT3 ---
    if "296" in v or "AFCO" in v:
        return ("Ferrari 296 GT3", PRESET_MAP_GT_NEO["GT3_296"], "GT3 296")
    if "720S" in v or "GARA" in v or "GCHAL" in v or "MCLAREN" in v:
        return ("McLaren 720S GT3 Evo", PRESET_MAP_GT_NEO["GT3_720S"], "GT3 720S")
    if "911" in v or "MANT" in v or ("PORSCHE" in v and "GT3" in v):
        return ("Porsche 911 GT3 R", PRESET_MAP_GT_NEO["GT3_911"], "GT3 911")
    if "M4" in v or "WRT" in v or ("BMW" in v and "GT3" in v):
        return ("BMW M4 GT3", PRESET_MAP_GT_NEO["GT3_M4"], "GT3 M4")
    if "MUSTANG" in v or "PROT" in v or "FORD" in v:
        return ("Ford Mustang GT3", PRESET_MAP_GT_NEO["GT3_MUSTANG"], "GT3 Mustang")
    if "LEXUS" in v or "RCF" in v or "AKKO" in v:
        return ("Lexus RC F GT3", PRESET_MAP_GT_NEO["GT3_RCF"], "GT3 RCF")
    if "CORVETTE" in v or "Z06" in v or "TFSP" in v or "VETTE" in v:
        return ("Corvette Z06 GT3.R", PRESET_MAP_GT_NEO["GT3_VETTE"], "GT3 Vette")
    if "HURACAN" in v or "IRON" in v or ("LAMBORGHINI" in v and "GT3" in v):
        return ("Lamborghini Huracan GT3 Evo2", PRESET_MAP_GT_NEO["GT3_296"], "GT3 296")
    if "AMG" in v or "MERCEDES" in v:
        return ("Mercedes-AMG GT3", PRESET_MAP_GT_NEO["GT3_M4"], "GT3 M4")
    if "VANTAGE" in v or "THOR" in v:
        return ("Aston Martin Vantage GT3", PRESET_MAP_GT_NEO["GTE_AMR"], "GTE AMR")

    # --- Hypercar / LMH / LMDh ---
    if "CADILLAC" in v or "CADIL" in v or "V-SERIES" in v or "VLMDH" in v or "WTR" in v:
        return ("Cadillac V-Series.R", PRESET_MAP_GT_NEO["HYP_CADILLAC"], "HYP Cadillac")
    if "PEUGEOT" in v or "PEUG" in v or "9X8" in v:
        return ("Peugeot 9X8", PRESET_MAP_GT_NEO["HYP_PEUGEOT"], "HYP Peugeot")
    if "VALKYRIE" in v or "THO7" in v or "007_" in v:
        return ("Aston Martin Valkyrie LMH", PRESET_MAP_GT_NEO["HYP_VALKYRIE"], "HYP Valkyrie")
    if "499P" in v or ("FERRARI" in v and "HYP" in v):
        return ("Ferrari 499P", PRESET_MAP_GT_NEO["HYP_CADILLAC"], "HYP Cadillac")
    if "963" in v:
        return ("Porsche 963", PRESET_MAP_GT_NEO["HYP_CADILLAC"], "HYP Cadillac")
    if "TOYOTA" in v or "GR010" in v or "TR010" in v:
        return ("Toyota GR010 Hybrid", PRESET_MAP_GT_NEO["HYP_CADILLAC"], "HYP Cadillac")
    if "ALPINE" in v or "A424" in v:
        return ("Alpine A424", PRESET_MAP_GT_NEO["HYP_CADILLAC"], "HYP Cadillac")
    if "SC63" in v:
        return ("Lamborghini SC63", PRESET_MAP_GT_NEO["HYP_CADILLAC"], "HYP Cadillac")
    if "BMW" in v and ("HYBRID" in v or "BMWMH" in v or "M_HYBRID" in v):
        return ("BMW M Hybrid V8", PRESET_MAP_GT_NEO["HYP_CADILLAC"], "HYP Cadillac")
    if "GMR001" in v or "GENESIS" in v:
        return ("Genesis GMR001 Hypercar", PRESET_MAP_GT_NEO["HYP_CADILLAC"], "HYP Cadillac")
    if "ISOTTA" in v:
        return ("Isotta Fraschini Tipo 6", PRESET_MAP_GT_NEO["HYP_CADILLAC"], "HYP Cadillac")

    # --- LMP2 ---
    if "ORECA" in v or "07_LMP2" in v or "VECTOR" in v or "LMP2" in v:
        return ("Oreca 07 LMP2", PRESET_MAP_GT_NEO["LM_P2"], "LM P2")

    # --- LMP3 ---
    if "GINETTA" in v or "G61" in v or "LMP3" in v or "DUQUEINE" in v or "LIGIER" in v:
        return ("Ginetta G61-LT-P325 Evo", PRESET_MAP_GT_NEO["LMP3_GINETTA"], "LMP3 Ginetta")

    # Fallback to user default GT NEO profile
    return (vehicle_identifier.strip(), PRESET_MAP_GT_NEO["DEFAULT"], "My GT Neo Default")


if __name__ == "__main__":
    test_cases = [
        "296_GT3.veh",
        "Ferrari 296 GT3",
        "McLaren 720S LMGT3 Evo",
        "Cadillac V-Series.R",
        "Oreca 07",
        "Peugeot 9x8",
        "Ford Mustang LMGT3",
        "Porsche 911 GT3 R LMGT3",
        "Lexus RCF LMGT3",
        "Aston Martin Valkyrie",
        "Ginetta G61-LT-P325",
        "Porsche 911 RSR",
        "Lamborghini Huracan GT3",
        "Unknown_Test_Car"
    ]
    print("=" * 70)
    print("       LMU VEHICLE TO SIMAGIC PRESET RESOLUTION VERIFICATION       ")
    print("=" * 70)
    for sample in test_cases:
        model, uuid, preset_name = resolve_vehicle_to_preset(sample)
        print(f"  {sample:<30} -> {model:<25} | [{preset_name}] ({uuid})")
