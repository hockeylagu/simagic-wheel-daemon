# WheelDaemon Roadmap: Automatic Car Profiles & CAN-FD Custom RPM LEDs

**Author:** Antigravity Research  
**Target Simulator:** Le Mans Ultimate (LMU)  
**Target Hardware:** Simagic Alpha EVO Sport Base + GT NEO Steering Wheel (over CAN-FD Quick Release)

---

## 1. Project Objectives

1. **Goal 1 (Profile Switching):** Automatically detect the vehicle loaded in Le Mans Ultimate and switch the active profile on both the **Wheelbase** and the **GT NEO steering wheel** without user intervention.
2. **Goal 2 (Custom RPM & Flag LED Engine over CAN-FD):** Overcome SimPro's generic linear RPM percentage calculation to provide **car-accurate rev lights, shift alerts, and pit limiter / TC patterns** on the GT NEO without requiring a Maglink USB cable (running 100% over the wheelbase CAN-FD quick release).

---

## 2. Goal 1 Architecture: Automatic Car Detection & Profile Switching

```
  +--------------------------------------------------------------+
  |                   Le Mans Ultimate (LMU)                     |
  |     Writes session & scoring data to shared memory           |
  |             `$rFactor2SMMP_Scoring$`                          |
  +--------------------------------------------------------------+
                                |
                                v (100% Read-Only Win32 mmap @ 2 Hz)
  +--------------------------------------------------------------+
  |                   WheelDaemon (Python Engine)                |
  |  1. Read `mVehicleInfo[playerID].mVehicleName`               |
  |  2. If vehicle changed (e.g. from 499P -> 296 GT3):          |
  |     Lookup preset UUIDs from `vehicle_profiles.json`         |
  +--------------------------------------------------------------+
                                |
                                v HTTP POST (Local REST API, Port 4010)
  +--------------------------------------------------------------+
  |                     SimPro Manager v3                        |
  |  POST /simpro/api/v3/preset_select_dev_config                |
  |  - Wheelbase Preset (Base rotation, FFB strength, dampening) |
  |  - GT NEO Preset (Clutch bite point, button maps, LED theme) |
  +--------------------------------------------------------------+
                                |
                                v CAN-FD Quick Release Pogo Pins
  +--------------------------------------------------------------+
  |                   GT NEO & Alpha EVO Base                    |
  |  Settings updated in volatile RAM. Ready to race instantly.  |
  +--------------------------------------------------------------+
```

### 2.1 Vehicle Mapping Database
You already have exact presets created in SimPro for almost all LMU cars. WheelDaemon will use a simple mapping file:

```json
{
  "Ferrari 296 LMGT3": {
    "wheel_preset_uuid": "<WHEEL_PRESET_UUID_296>",
    "base_preset_uuid": "<BASE_PRESET_UUID>"
  },
  "McLaren 720S LMGT3": {
    "wheel_preset_uuid": "<WHEEL_PRESET_UUID_720S>",
    "base_preset_uuid": "<BASE_PRESET_UUID>"
  },
  "Porsche 911 LMGT3.R": {
    "wheel_preset_uuid": "<WHEEL_PRESET_UUID_911>",
    "base_preset_uuid": "<BASE_PRESET_UUID>"
  },
  "Cadillac V-Series.R": {
    "wheel_preset_uuid": "<WHEEL_PRESET_UUID_CADILLAC>",
    "base_preset_uuid": "<BASE_PRESET_UUID>"
  },
  "Oreca 07 Gibson": {
    "wheel_preset_uuid": "<WHEEL_PRESET_UUID_ORECA>",
    "base_preset_uuid": "<BASE_PRESET_UUID>"
  }
}
```

---

## 3. Goal 2 Architecture: The CAN-FD Custom RPM & LED Engine

### 3.1 The Problem with SimPro's Default RPM Calculation
* **Linear vs Non-Linear Curves:** In real cars (and LMU's physics engine), rev lights are **not** evenly spaced across the entire RPM range (0–8,500 RPM). Instead, the lights only start illuminating in the top 20%–30% of the usable powerband (e.g. starting at 6,500 RPM and finishing at 8,200 RPM).
* **Per-Gear Shift Points:** In some cars, redline RPM shifts depending on the gear.
* **Telemetry Indicators in Rev Strip:** Some cars use the outer RPM LEDs to signal Pit Limiter or Traction Control activity, rather than using separate buttons.

### 3.2 How We Solve This Over CAN-FD (3 Viable Solutions)

#### Solution A: The SimPro CAN-FD Bridge (`ctrl_by_simhub`)
* **How it works:**
  1. WheelDaemon enables the official SimHub delegation flag:
     ```http
     POST http://127.0.0.1:4010/simpro/api/v3/set_device_simhub_data
     {
       "product_uuid": "33947648",
       "device_uuid": "33947648",
       "ctrl_by_simhub": true
     }
     ```
  2. SimHub generates its detailed custom LED animations using SimHub's vehicle profiles.
  3. SimHub sends its frames to SimPro.
  4. SimPro acts as the **CAN-FD Gateway**, streaming the frames through `SCommUsbHid::writeOutReportCanfdSync` across the quick release to the GT NEO.
  5. **Result:** Full SimHub custom LED capability over CAN-FD without a Maglink USB cable.

#### Solution B: Car-Calibrated SimPro Preset Tuning (Native CAN-FD)
* **How it works:**
  1. For each car profile in SimPro, we tune the `rpm_lights` configuration with the exact start RPM, max RPM, and color layout for that specific vehicle.
  2. When WheelDaemon selects the profile via `preset_select_dev_config`, SimPro loads that car's tuned rev strip parameters.
  3. SimPro handles the live telemetry evaluation natively.
  4. **Pros:** Extremely lightweight, requires no secondary software running in the background during driving.

#### Solution C: WheelDaemon Direct Live Frame Streaming (Autonomous Mode)
* **How it works:**
  1. WheelDaemon reads high-frequency physics telemetry directly from `$rFactor2SMMP_Telemetry$` (at 60 Hz).
  2. WheelDaemon computes custom RPM curves, non-linear shift points, pit limiter flashing, and TC indicators.
  3. WheelDaemon pushes the real-time LED array into SimPro using the internal preview/control pipeline (`start_preview_preset_item` / `preset_set_dev_config`).

---

## 4. Implementation Phasing

### Phase 1: Core Automation (Goal 1)
* [x] Reverse engineer SimPro daemon, IPC, and local REST API.
* [x] Verify live device communication and read active wheelbase / GT NEO presets.
* [ ] Build LMU Shared Memory Reader (`lmu_reader.py`) to extract `mVehicleName`.
* [ ] Build `profile_switcher.py` to map cars to presets and trigger API switches.
* [ ] Test live in LMU (switching between a Hypercar and GT3).

### Phase 2: Custom RPM LEDs over CAN-FD (Goal 2)
* [ ] Verify the `ctrl_by_simhub` CAN-FD bridge between SimHub and SimPro on the live wheel.
* [ ] Compare live telemetry RPM from `$rFactor2SMMP_Telemetry$` with the GT NEO rev light behavior.
* [ ] Implement custom non-linear shift light curves and flag overrides for LMU vehicles.
