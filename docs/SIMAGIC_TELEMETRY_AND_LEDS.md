# Simagic Telemetry & LED Engine: Reverse-Engineering & Architecture

**Author:** Antigravity Research  
**Target System:** SimPro Manager v3 / Simagic Alpha EVO & GT NEO Ecosystem  
**Subject:** In-depth technical analysis of how SimPro ingests game telemetry, calculates RPM rev lights, evaluates yellow/blue flag alerts and driver assists (ABS/TC), and transmits LED data to the steering wheel.

---

## 1. Executive Summary & Pipeline Overview

When a racing simulation is running, Simagic’s ecosystem operates a real-time, closed-loop telemetry and lighting engine running at **60 Hz to 100 Hz**:

```
+-------------------------------------------------------------------------------------------------+
|                                     1. SIMULATION LAYER                                         |
|  Le Mans Ultimate / rFactor 2                                     F1 / EA WRC / Dirt Rally      |
|  - Writes to Windows Shared Memory Buffers                        - Sends UDP Packets           |
|    (`$rFactor2SMMP_Telemetry$`, `$rFactor2SMMP_Scoring$`)          (Ports 20777, 20888, etc.)   |
+-------------------------------------------------------------------------------------------------+
                                                |
                                                v
+-------------------------------------------------------------------------------------------------+
|                                 2. INGESTION & DATA NORMALIZATION                               |
|  `STelemetryDataSource::fetchingData()` & `STelemetryEngine::exec()`                            |
|  - Reads shared memory structs or parses incoming UDP datagrams                                 |
|  - Normalizes raw values into 266 standard telemetry channels:                                  |
|    `CarSettings_currentDisplayedRPMPercent`, `yellowFlag`, `isAbsActive`, `isTcActive`, etc.    |
+-------------------------------------------------------------------------------------------------+
                                                |
                                                v
+-------------------------------------------------------------------------------------------------+
|                                3. EFFECT EVALUATION & PRIORITY ENGINE                           |
|  `SRpmLightEffect`                                    `SLightGroupTelemetrysTriggerEffect`      |
|  - Compares RPM % against shift thresholds            - Evaluates Flags (Yellow, Blue, Red)     |
|  - Calculates LED index fill (Left->Right / Center)   - Evaluates Assists (ABS, TC, Pit Limiter)|
|  - Triggers redline flash (`RPM_REDLINE`)             - Resolves priority overrides             |
+-------------------------------------------------------------------------------------------------+
                                                |
                                                v (RGB Output Frame: [LED_0, LED_1, ... LED_N])
+-------------------------------------------------------------------------------------------------+
|                               4. HARDWARE TRANSMISSION (USB & CAN-FD)                           |
|  `SCommUsbHid::writeOutReportCanfdSync()`                                                       |
|  - Packages RGB frames into Vendor HID Output Reports on USB Interface `MI_01` (VID 0x3670)     |
|  - Microcontroller sends frames across Quick Release CAN-FD contact pins (or 2.4GHz RF)        |
|  - GT NEO internal controller updates addressable RGB LEDs                                      |
+-------------------------------------------------------------------------------------------------+
```

---

## 2. Ingestion Layer: How SimPro Reads Live Game Data

SimPro supports two telemetry ingestion paradigms depending on the simulator:

### 2.1 Le Mans Ultimate & rFactor 2: Windows Shared Memory (MMAP)
SimPro ships with the official rFactor 2 shared memory plugin:
`C:\Program Files (x86)\Simagic\Simpro3\game_plugin\LMU & RF2\rFactor2SharedMemoryMapPlugin64.dll`

When LMU runs, the plugin creates named memory-mapped files in the Windows kernel:

1. **`$rFactor2SMMP_Telemetry$` (High-Speed Physics & Engine Data):**
   * `mEngineRPM`: Current instantaneous engine revolutions per minute.
   * `mEngineMaxRPM`: Maximum engine RPM (rev limiter threshold).
   * `mSpeed`: Ground velocity.
   * `mGear`: Current gear (-1 = Reverse, 0 = Neutral, 1-8 = Forward).
   * `mUnfilteredThrottle` / `mUnfilteredBrake` / `mUnfilteredClutch`: Live pedal inputs.

2. **`$rFactor2SMMP_Scoring$` (Race Management & Session State):**
   * `mSectorFlag[3]`: Sector-specific flag states (0 = Green, 1 = Yellow, 2 = Blue).
   * `mYellowFlagState`: Detailed yellow flag status across sectors.
   * `mGamePhase`: Practice, Qualifying, Formation, Race, Full-Course Yellow, Safety Car.
   * `mInPits`: Boolean whether the vehicle is currently in pit lane.
   * `mVehicleInfo[mPlayerCarID].mVehicleName`: Current car model name.

`STelemetryDataSource::fetchingData()` reads these shared memory buffers using standard Win32 `OpenFileMapping` and `MapViewOfFile` APIs at zero performance cost and zero anti-cheat risk.

### 2.2 Other Sims (F1, EA WRC, Dirt Rally): UDP Telemetry Sockets
For games that do not support shared memory, SimPro spins up local UDP listeners specified in `%LOCALAPPDATA%\Simagic\simpro3\config\telemetry\telemetry_port.data`:
* **F1 2018–2024**: UDP Port `20777`
* **EA WRC**: UDP Port `20888`
* **DiRT Rally 2.0**: UDP Port `20777`

---

## 3. Telemetry Normalization (The 266 Standard Channels)

Once raw telemetry arrives, `STelemetryEngine` normalizes the game-specific variables into a standardized 266-channel dictionary (defined in `%LOCALAPPDATA%\Simagic\simpro3\config\telemetry\telemetry.data`).

This schema follows the **SimHub telemetry property architecture**:

| Channel Name | Category | Type | Purpose |
| :--- | :--- | :--- | :--- |
| `CarSettings_currentDisplayedRPMPercent` | Engine & Power | `float` (0.0 – 1.0) | Normalized engine RPM relative to shift range |
| `CarSettings_RedLineRPM` | Driver Assist | `float` | Exact RPM threshold for redline/shift alert |
| `CarSettings_RPMRedLineReached` | Driving Control | `bool` | True when RPM has exceeded the shift point |
| `blinkingGearUP` | Driving Control | `bool` | High-frequency flash pulse for optimal shift |
| `yellowFlag` | Flags | `bool` / `int` | Track sector has active yellow flag hazard |
| `blueFlag` | Flags | `bool` | Faster car approaching to lap player |
| `greenFlag` | Flags | `bool` | Track is clear / race restart |
| `redFlag` | Flags | `bool` | Session stopped |
| `checkeredFlag` | Flags | `bool` | Race finished |
| `isAbsActive` | Driver Assist | `bool` | Antilock Brake System currently pulsing |
| `isTcActive` | Driver Assist | `bool` | Traction Control currently cutting power |
| `isInPit` | Race Info | `bool` | Car is inside the pit lane |
| `isPitLimiterOn` | Driving Control | `bool` | Speed limiter active |

---

## 4. Effect Evaluation Engine: Computing LED States

Lighting calculations are split into two C++ subsystems inside `simpro3.exe`:

### 4.1 RPM Rev Light Strip: `SRpmLightEffect`
The steering wheel’s top LED bar (on the GT NEO, 15 addressable RGB LEDs) is controlled by `SRpmLightEffect::exec()` and `SRpmLightEffect::handleRpmLightEffectPreset()`:

1. **Threshold Calculation**:
   * SimPro reads the vehicle’s idle, first-light, and max redline RPM:
     $$\text{RPM}_{\text{norm}} = \frac{\text{currentRPM} - \text{startRPM}}{\text{redlineRPM} - \text{startRPM}}$$
2. **Fill Mode Styles**:
   * **Left-to-Right**: LEDs ignite from LED 0 to LED 14 sequentially.
   * **Center-Outwards (Split)**: LEDs ignite from the center (LED 7) moving outward towards both sides simultaneously (standard Formula / GT3 style).
   * **Right-to-Left**: Reverse sequence.
3. **Color Progression**:
   * Evaluates user color zones (typically 5 Green &rarr; 5 Red &rarr; 5 Blue).
4. **Redline Alert (`RPM_REDLINE`)**:
   * When `CarSettings_RPMRedLineReached == true`, the fill state switches to a high-frequency flashing mode (all LEDs strobe in user-selected color, e.g. solid white `#FFFFFF` or blue `#0006FF` at 10 Hz).

### 4.2 Flags & Driver Assists: `SLightGroupTelemetrysTriggerEffect`
The GT NEO has:
* 15 RPM LEDs
* 2 Side Flag / Spotter LED bars (4 LEDs on each side)
* 4 Thumb Rotary dial backlight halos
* 2 Front Rotary dial backlights
* 10 Button RGB backlights

`SLightGroupTelemetrysTriggerEffect` listens for state changes on trigger channels:

#### 1. Yellow Flag (`FLAG_YELLOW`)
* **Trigger Condition**: `yellowFlag == true` or `mYellowFlagState > 0`
* **Hardware Reaction**:
  * Side spotter LED bars flash yellow (`#FFFD51` / `#FFC107`).
  * On profiles configured with flag override, the entire top RPM strip pulses yellow until the hazard clear (`greenFlag`) signal is detected.

#### 2. Blue Flag (`FLAG_BLUE`)
* **Trigger Condition**: `blueFlag == true`
* **Hardware Reaction**:
  * Side spotter bars flash blue (`#0006FF`) to indicate a faster car is lapping from behind.

#### 3. Traction Control Active (`TC_ACTIVE`)
* **Trigger Condition**: `isTcActive == true`
* **Hardware Reaction**:
  * Flashes the configured TC Rotary knob halo or assigned button LED in amber/red (`#FF6C00`).

#### 4. ABS Active (`ABS_ACTIVE`)
* **Trigger Condition**: `isAbsActive == true`
* **Hardware Reaction**:
  * Flashes the configured ABS Rotary knob halo in bright cyan/blue (`#00FFFC`).

#### 5. Pit Limiter (`PIT_LIMITER` / `IS_IN_PIT`)
* **Trigger Condition**: `isPitLimiterOn == true` or `isInPit == true`
* **Hardware Reaction**:
  * Alternate flashing pattern (e.g., alternating odd/even LEDs or pulsing blue/yellow) across the RPM bar while in the pit box/lane.

---

## 5. Priority and Conflict Resolution

When multiple telemetry conditions occur simultaneously (for example, revving near redline while in a yellow flag sector), `SLightGroupTelemetrysTriggerEffect` resolves conflicts using a strict **priority hierarchy**:

```
[ HIGHEST PRIORITY ]
  1. RED FLAG / SAFETY CAR / SESSION STOPPED
  2. PIT LIMITER (When limiter switch is engaged)
  3. YELLOW FLAG HAZARD OVERRIDE
  4. RPM REDLINE FLASH (Shift point reached)
  5. NORMAL RPM FILL STRIP
  6. DRIVER ASSIST FLASH (ABS / TC on Rotary Halo LEDs)
  7. STATIC BACKLIGHT (Base color scheme)
[ LOWEST PRIORITY ]
```

Because ABS and TC alerts target the rotary dial halos and button backlights, they do not disrupt the RPM rev bar unless specifically configured by the user.

---

## 6. How LED Patterns Are Structured & Saved

LED patterns are stored in **`user.db`** (`%LOCALAPPDATA%\Simagic\Simpro3\storage\user.db`) as a Google Protocol Buffers binary blob inside the **`presetData`** column of the `preset` table. 

When queried via the local REST API (`POST /simpro/api/v3/preset_get_dev_config`), SimPro deserializes this Protobuf blob into two primary lighting trees:

### 6.1 The RPM Rev Light Strip Schema (`rpm_lights`)
Located under key `"rpm_lights"` &rarr; `"1"`:
* **`brightness`**: Master brightness percentage (e.g., `100`).
* **`mode`**: Fill direction/pattern:
  * `"X"` or `"left_to_right"`: Progressive fill.
  * `"split"`: Center-outward symmetric fill.
* **`max_rpm`**: RPM ceiling used for threshold calculation (e.g. `20000`).
* **`color`**: A 15-element array containing the exact hexadecimal RGB color for each physical LED on the GT NEO strip. For example, in your **`GT3 296`** preset:
  ```json
  [
    "#000000", "#000000", "#000000", "#000000",
    "#00ff84", "#00ff84",
    "#fffd51", "#fffd51",
    "#ff0054", "#ff0054",
    "#000000", "#000000", "#000000", "#000000", "#000000"
  ]
  ```
* **`redline`**: Shift flash definition:
  * `enabled`: `true`
  * `key`: `"RPM_REDLINE"`
  * `active_effect`: `"breath"`, `"flash"`, or `"mono"`
  * `foregroud_color`: 15-element array defining the strobe color (e.g. `#49AA19`).

---

### 6.2 The Button & Rotary Dial Multi-Layer Stack (`led_buttons`)
The GT NEO has 10 RGB back-illuminated buttons and rotary dial halos. Each physical control contains a **layered effect stack**:

```json
"led_buttons": {
  "8": {
    "button": { "code": 8, "label": "" },
    "led": {
      "color": "#000000",
      "items": [
        { "key": "STATIC_EFFECT", "enabled": false, "light": { "configs": { "mono": { "foregroud_color": ["#00fffc"] } } } },
        { "key": "ABS_ACTIVE",    "enabled": false, "light": { "configs": { "mono": { "foregroud_color": ["#00fffc"] } } } },
        { "key": "TC_ACTIVE",     "enabled": false, "light": { "configs": { "mono": { "foregroud_color": ["#00fffc"] } } } },
        { "key": "PIT_LIMITER",   "enabled": true,  "light": { "configs": { "mono": { "foregroud_color": ["#00fffc"] } } } },
        { "key": "DRS_ON",        "enabled": false, "light": { "configs": { "mono": { "foregroud_color": ["#00fffc"] } } } },
        { "key": "FLAG",          "enabled": false, "light": { "configs": { "mono": { "foregroud_color": ["#00fffc"] } } } }
      ]
    }
  }
}
```

#### How the Multi-Layer Evaluation Works:
For every button, all 6 effect layers are always present in the preset:
1. **`STATIC_EFFECT`**: Idle ambient lighting color.
2. **`ABS_ACTIVE`**: Pulsates when ABS triggers.
3. **`TC_ACTIVE`**: Pulsates when Traction Control triggers.
4. **`PIT_LIMITER`**: Overrides color when Pit Limiter is engaged (e.g., Button #8 in your GT3 296 profile is set to `#00fffc` Cyan).
5. **`DRS_ON`**: Illuminates when DRS flap is open.
6. **`FLAG`**: Alerts for sector hazard flags.

When a telemetry event fires, SimPro iterates through the layer stack; if `enabled: true`, the active telemetry effect overrides the `STATIC_EFFECT` color for that specific button.


---

## 7. Hardware Transmission: How SimPro Sends LEDs to the Wheel

Once SimPro generates the final array of RGB bytes for each LED index:

1. **Vendor HID Output Report**:
   * SimPro opens Windows HID communication via `hid.dll` on interface `MI_01` (VID `0x3670`, PID `0x0500`).
   * Calls `SCommUsbHid::writeOutReportCanfdSync()`.
2. **CAN-FD Protocol Across the Quick Release**:
   * The Alpha EVO wheelbase controller receives the vendor HID output report.
   * It encapsulates the LED data payload into a high-speed **CAN-FD (Controller Area Network Flexible Data-Rate)** frame.
   * The frame travels through the spring-loaded gold contact pins in the center of the Simagic Quick Release mechanism directly into the GT NEO wheel hub.
   * *(Note: If the wheel is using wireless mode without contact pins, the base broadcasts the CAN frame via its internal 2.4GHz RF transceiver).*
3. **GT NEO Onboard Microcontroller**:
   * An onboard STM32/ARM microcontroller decodes the CAN-FD frame and clocks the raw RGB data out to the individual WS2812/SK6812 LED strings.

---

## 8. Summary for WheelDaemon Integration

* **Native SimPro does all the heavy lifting**: You do **not** need to write a custom LED driver or reverse-engineer CAN-FD frames.
* **Why vehicle switching matters for LEDs**:
  * Each vehicle in LMU has different rev limits, shift points (e.g. 8,500 RPM for Ferrari 296 GT3 vs 10,500 RPM for Oreca 07 LMP2), and different dial assignments.
  * When WheelDaemon switches your GT NEO profile via `preset_select_dev_config`, SimPro automatically updates the RPM thresholds, rev light colors, and assist mappings for that specific car.
  * SimPro continues to read LMU's shared memory and updates all RPM lights, yellow flags, and ABS/TC indicators seamlessly.
