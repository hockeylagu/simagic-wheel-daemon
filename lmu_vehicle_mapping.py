"""
LMU Vehicle Mapping Engine
Extracts vehicle identity from LMU's REST API (:6397) and Shared Memory ($rFactor2SMMP_Scoring$)
and resolves it directly to the user's Simagic GT NEO and Base preset UUIDs.
Derived from LMULapTime domain vehicle mapping logic.
"""

from typing import Optional, Tuple, Dict, Any

# User's Wheelbase Preset (Alpha EVO Sport)
DEFAULT_BASE_PRESET_UUID = "<BASE_PRESET_UUID>"  # "My LeMans Ultimate"

# User's GT NEO Presets
PRESET_MAP_GT_NEO = {
    # GT3 / LMGT3
    "GT3_296":     "<WHEEL_PRESET_UUID_296>",  # 'GT3 296'
    "GT3_720S":    "<WHEEL_PRESET_UUID_720S>",  # 'GT3 720S'
    "GT3_911":     "<WHEEL_PRESET_UUID_911>",  # 'GT3 911'
    "GT3_M4":      "<WHEEL_PRESET_UUID_M4>",  # 'GT3 M4'
    "GT3_MUSTANG": "<WHEEL_PRESET_UUID_MUSTANG>",  # 'GT3 Mustang'
    "GT3_RCF":     "<WHEEL_PRESET_UUID_RCF>",  # 'GT3 RCF'
    "GT3_VETTE":   "<WHEEL_PRESET_UUID_VETTE>",  # 'GT3 Vette'
    
    # GTE
    "GTE_AMR":     "<WHEEL_PRESET_UUID_AMR>",  # 'GTE AMR'
    
    # Hypercar / LMH / LMDh
    "HYP_CADILLAC": "<WHEEL_PRESET_UUID_CADILLAC>",  # 'HYP Cadillac'
    "HYP_PEUGEOT":  "<WHEEL_PRESET_UUID_PEUGEOT>",  # 'HYP Peugeot'
    "HYP_VALKYRIE": "<WHEEL_PRESET_UUID_VALKYRIE>",  # 'HYP Valkyrie'
    
    # LMP2 & LMP3
    "LM_P2":        "<WHEEL_PRESET_UUID_LMP2>",  # 'LM P2'
    "WEC_P2":       "<WHEEL_PRESET_UUID_WECP2>",  # 'WEC P2'
    "LMP3_GINETTA": "<WHEEL_PRESET_UUID_GINETTA>",  # 'LMP3 Ginetta'
    
    # Fallback default
    "DEFAULT":      "<WHEEL_PRESET_UUID_DEFAULT>",  # 'My GT Neo Default'
}


def resolve_vehicle_to_preset(vehicle_identifier: str) -> Tuple[str, str, str]:
    """
    Takes any raw vehicle string (vehFile, model name, carType, or shared memory mVehicleName)
    and resolves it to:
    (Friendly Model Name, Target GT NEO Preset UUID, Preset Name)
    """
    if not vehicle_identifier:
        return ("Default", PRESET_MAP_GT_NEO["DEFAULT"], "My GT Neo Default")

    v = vehicle_identifier.upper()

    # --- GTE ---
    if "DSTATI" in v or "AMR" in v and "GTE" in v:
        return ("Aston Martin Vantage GTE", PRESET_MAP_GT_NEO["GTE_AMR"], "GTE AMR")
    if "RSR" in v or "REXY" in v or "488" in v or "KESSEL" in v:
        return ("GTE Vehicle", PRESET_MAP_GT_NEO["GTE_AMR"], "GTE AMR")

    # --- GT3 / LMGT3 ---
    if "296" in v or "AFCO" in v:
        return ("Ferrari 296 GT3", PRESET_MAP_GT_NEO["GT3_296"], "GT3 296")
    if "720S" in v or "GARA" in v or "GCHAL" in v or "MCLAREN" in v:
        return ("McLaren 720S GT3 Evo", PRESET_MAP_GT_NEO["GT3_720S"], "GT3 720S")
    if "911" in v or "MANT" in v or "PORSCHE" in v and "GT3" in v:
        return ("Porsche 911 GT3 R", PRESET_MAP_GT_NEO["GT3_911"], "GT3 911")
    if "M4" in v or "WRT" in v or "BMW" in v and "GT3" in v:
        return ("BMW M4 GT3", PRESET_MAP_GT_NEO["GT3_M4"], "GT3 M4")
    if "MUSTANG" in v or "PROT" in v or "FORD" in v:
        return ("Ford Mustang GT3", PRESET_MAP_GT_NEO["GT3_MUSTANG"], "GT3 Mustang")
    if "LEXUS" in v or "RCF" in v or "AKKO" in v:
        return ("Lexus RC F GT3", PRESET_MAP_GT_NEO["GT3_RCF"], "GT3 RCF")
    if "CORVETTE" in v or "Z06" in v or "TFSP" in v or "VETTE" in v:
        return ("Corvette Z06 GT3.R", PRESET_MAP_GT_NEO["GT3_VETTE"], "GT3 Vette")

    # --- Hypercar / LMH / LMDh ---
    if "CADILLAC" in v or "CADIL" in v or "V-SERIES" in v or "VLMDH" in v or "WTR" in v:
        return ("Cadillac V-Series.R", PRESET_MAP_GT_NEO["HYP_CADILLAC"], "HYP Cadillac")
    if "PEUGEOT" in v or "PEUG" in v or "9X8" in v:
        return ("Peugeot 9X8", PRESET_MAP_GT_NEO["HYP_PEUGEOT"], "HYP Peugeot")
    if "VALKYRIE" in v or "THO7" in v or "007_" in v:
        return ("Aston Martin Valkyrie LMH", PRESET_MAP_GT_NEO["HYP_VALKYRIE"], "HYP Valkyrie")
    if "499P" in v or "FERRARI" in v and "HYP" in v:
        return ("Ferrari 499P", PRESET_MAP_GT_NEO["HYP_CADILLAC"], "HYP Cadillac")
    if "963" in v:
        return ("Porsche 963", PRESET_MAP_GT_NEO["HYP_CADILLAC"], "HYP Cadillac")
    if "TOYOTA" in v or "GR010" in v or "TR010" in v:
        return ("Toyota GR010 Hybrid", PRESET_MAP_GT_NEO["HYP_CADILLAC"], "HYP Cadillac")
    if "ALPINE" in v or "A424" in v:
        return ("Alpine A424", PRESET_MAP_GT_NEO["HYP_CADILLAC"], "HYP Cadillac")
    if "BMW" in v and ("HYBRID" in v or "BMWMH" in v):
        return ("BMW M Hybrid V8", PRESET_MAP_GT_NEO["HYP_CADILLAC"], "HYP Cadillac")

    # --- LMP2 ---
    if "ORECA" in v or "LMP2" in v or "VECTOR" in v or "07_LMP2" in v:
        return ("Oreca 07 LMP2", PRESET_MAP_GT_NEO["LM_P2"], "LM P2")

    # --- LMP3 ---
    if "GINETTA" in v or "G61" in v or "LMP3" in v:
        return ("Ginetta G61-LT-P325 Evo", PRESET_MAP_GT_NEO["LMP3_GINETTA"], "LMP3 Ginetta")

    # Default fallback
    return (vehicle_identifier, PRESET_MAP_GT_NEO["DEFAULT"], "My GT Neo Default")


if __name__ == "__main__":
    test_samples = [
        "296_GT3.veh",
        "McLaren 720S LMGT3 Evo",
        "Cadillac V-Series.R",
        "Oreca 07",
        "Peugeot 9x8",
        "Ford Mustang LMGT3",
        "Porsche 911 GT3 R LMGT3",
        "Lexus RCF LMGT3",
        "Aston Martin Valkyrie",
        "Ginetta G61-LT-P325",
        "Unknown_Test_Car"
    ]
    print("================================================================")
    print("          LMU VEHICLE TO SIMAGIC PRESET RESOLUTION TEST         ")
    print("================================================================")
    for sample in test_samples:
        model, uuid, preset_name = resolve_vehicle_to_preset(sample)
        print(f"'{sample}' -> Model: '{model}' | Preset: '{preset_name}' (UUID: {uuid})")
