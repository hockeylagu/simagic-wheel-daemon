# LMU Telemetry Discovery & Simagic Vehicle Mapping Reference

**Source Repository:** `LMULapTime` (`C:\Documents\LMULapTime`)  
**Target Integration:** `WheelDaemon` (`C:\Documents\WheelDeamon`)  
**Scope:** Only the specific API endpoints and vehicle tokens required for automatic profile switching.

---

## 1. LMU Embedded REST API Discovery

Le Mans Ultimate hosts an internal HTTP REST API running directly on:
```
http://localhost:6397
```

### The Primary Vehicle Detection Endpoint: `GET /navigation/state`
Returns the simulation's navigation lifecycle and the currently selected/loaded car.

* **URL:** `http://localhost:6397/navigation/state`
* **Transport:** HTTP GET (Port 6397, no auth required)
* **Response Payload (`loadingStatus.loadingData`):**
  ```json
  {
    "loadingStatus": {
      "loading": false,
      "loadingData": "{\"selectedCar\":{\"classes\":[\"LMGT3\"],\"manufacturer\":\"Ferrari\",\"number\":\"54\",\"team\":\"AF Corse\",\"vehFile\":\"296_GT3.veh\"}}"
    },
    "state": {
      "gamePhase": "SESSION_ACTIVE",
      "gameState": "GSTATE_DRIVING",
      "navigationState": "NAV_DRIVE"
    }
  }
  ```

### Why `GET /navigation/state` is Ideal:
1. **Available Early**: Returns the vehicle while still on the loading screen, in the garage, or sitting in the pits.
2. **Deterministic File Identity**: The `vehFile` string (e.g., `296_GT3.veh`, `ORECA_07.veh`) eliminates ambiguity from livery variations or custom team skins.

---

## 2. Vehicle Token Resolution Matrix

Extracted from `LMULapTime/shared/domain/vehicleMapping.ts` and mapped directly to your Simagic presets:

| In-Game Token / vehFile | Detected Model | Target Profile Name |
| :--- | :--- | :--- |
| `296`, `AFCO` | **Ferrari 296 GT3** | **`GT3 296`** |
| `720S`, `GARA`, `GCHAL` | **McLaren 720S GT3 Evo** | **`GT3 720S`** |
| `911`, `MANT` | **Porsche 911 GT3 R** | **`GT3 911`** |
| `M4`, `WRT` | **BMW M4 GT3** | **`GT3 M4`** |
| `MUSTANG`, `PROT` | **Ford Mustang GT3** | **`GT3 Mustang`** |
| `RCF`, `LEXUS`, `AKKO` | **Lexus RC F GT3** | **`GT3 RCF`** |
| `CORVETTE`, `Z06`, `TFSP` | **Corvette Z06 GT3.R** | **`GT3 Vette`** |
| `DSTATI`, `AMR GTE` | **Aston Martin Vantage GTE** | **`GTE AMR`** |
| `CADILLAC`, `V-SERIES`, `WTR` | **Cadillac V-Series.R** | **`HYP Cadillac`** |
| `9X8`, `PEUGEOT` | **Peugeot 9X8** | **`HYP Peugeot`** |
| `VALKYRIE`, `007_`, `THO7` | **Aston Martin Valkyrie LMH** | **`HYP Valkyrie`** |
| `ORECA`, `LMP2`, `VECTOR` | **Oreca 07 LMP2** | **`LM P2`** |
| `GINETTA`, `G61` | **Ginetta G61-LT-P325 Evo** | **`LMP3 Ginetta`** |
| *(Any Unrecognized Vehicle)* | Fallback Default | **`Default Profile`** |

*Note: Wheelbase profile is simultaneously assigned to the configured wheelbase profile.*


---

## 3. Fallback Mechanism: Shared Memory (`$rFactor2SMMP_Scoring$`)

If the embedded web server on port 6397 is blocked or during active on-track sessions where HTTP polling is paused:
* WheelDaemon reads `$rFactor2SMMP_Scoring$`.
* Requires the rF2 Shared Memory Map plugin to be enabled in LMU.
* The daemon walks `mVehicles[0..mNumVehicles)` and picks the record with `mIsPlayer` set.
* Vehicle name / class fields: `mVehicleName` / `mVehicleClass` (the class feeds the class-aware mapping).
* Reads are retried when `mVersionUpdateBegin != mVersionUpdateEnd` (buffer mid-write).
* Pass the string into `resolve_vehicle_to_preset(name, vehicle_class)` in [`vehicle_mapping.py`](../src/simagic_daemon/vehicle_mapping.py).
