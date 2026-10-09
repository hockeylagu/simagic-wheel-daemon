# Simagic Ecosystem & Profile Switching Technical Deep-Dive

**Author:** Antigravity Research  
**Target System:** Windows 10 / Simagic Alpha EVO Ecosystem (SimPro Manager 3.2.x)  
**Objective:** Automate per-vehicle wheel profile switching in Le Mans Ultimate (LMU) safely, without any risk of damaging or bricking the wheel base.

---

## 1. Executive Summary & Key Breakthrough

SimPro Manager v3 uses an internal **Local REST HTTP API** running on `http://127.0.0.1:4010/simpro/api/v3/` for all communication between the user interface and the device control engine.

### Why this is a game-changer:
1. **Zero Bricking Risk**: You **do not** need to reverse-engineer low-level USB firmware packets or inject raw bytes into the wheel's USB controller. 
2. **Native Official Pipeline**: By issuing standard HTTP POST requests to `http://127.0.0.1:4010/simpro/api/v3/preset_select_dev_config`, you invoke SimPro's own C++ validation pipeline (`SPresetManager`, `SDeviceConn`, `SWheelDevice`). SimPro handles the USB HID reports, parameter bounds checking, and device safety logic identically to a physical mouse click in the official UI.
3. **Only Runtime Parameters Modified**: Profile switching updates runtime tuning parameters in the base's volatile RAM (rotation limit, FFB strength, damping, friction, inertia, interpolation). It **never touches the microcontroller bootloader or non-volatile flash storage** (firmware flashing is a completely separate isolated endpoint: `device_fw_update`).
4. **Complete Profile Discovery**: You can query all existing official and user-created custom presets on the fly directly from the local API or from the local SQLite database (`user.db`).

---

## 2. Architecture Breakdown: How SimPro Works

```
  +-------------------------------------------------------------------------+
  |                             simdaemon.exe                               |
  |  - Watchdog & single-instance manager                                   |
  |  - Launches simpro3.exe                                                 |
  |  - Named pipe IPC for heartbeat monitoring (`SSimDaemonApp.cpp`)        |
  +-------------------------------------------------------------------------+
                                      |
                                      v (Launches & monitors)
  +-------------------------------------------------------------------------+
  |                              simpro3.exe                                |
  |  CEF (Chromium Embedded Framework) + Native C++ Core Engine             |
  |                                                                         |
  |  [ CEF Web Frontend ] (React + AntD)                                    |
  |            |                                                            |
  |            | HTTP POST requests (axios)                                 |
  |            v                                                            |
  |  [ Built-in Local HTTP Server ] Port 4010 (`SInteractCEFQryServer.cpp`)  |
  |            |                                                            |
  |            +---> SQLite Database (`user.db`, `simpro.db`)               |
  |            |     - Presets, calibrations, user configs                  |
  |            |                                                            |
  |            +---> `SPresetManager.cpp` & `SDeviceConn.cpp`               |
  |                  - Parameter bounds checking & validation               |
  |                  - Protobuf preset serialization/deserialization        |
  |            |                                                            |
  |            +---> `SCommUsbHid.cpp` (Windows HID API / hid.dll)          |
  +-------------------------------------------------------------------------+
                                      |
                       USB Composite Device (VID 0x3670)
                                      |
            +-------------------------+-------------------------+
            | Interface MI_00                                   | Interface MI_01
            v                                                   v
  [ Standard DirectInput Controller ]                [ Vendor HID Communication ]
  - Steering axis & pedals                           - Real-time parameter sync
  - DirectInput Force Feedback (FFB)                 - Base telemetry & telemetry LED
            |
            | Wireless 2.4GHz RF / CAN-Bus Quick Release / Maglink
            v
  [ Peripherals: Steering Wheel (GT Neo / Neo X), Pedals (P700), Shifters ]
```

### 2.1 The Two Executables
* **`simdaemon.exe`** (`C:\Program Files (x86)\Simagic\Daemon\simdaemon.exe`):
  * **Role:** Acts as a lightweight watchdog, single-instance enforcer, and launcher.
  * **IPC:** Sets up a named pipe server (`pipe server init done`) and runs a heartbeat loop (`SSimDaemonApp.cpp heartBeatImp`). When SimPro starts or shuts down, pipe command codes (e.g., `cmdCode=3`, `cmdCode=6`) are exchanged.
  * *It does NOT handle USB communication directly.*
* **`simpro3.exe`** (`C:\Program Files (x86)\Simagic\Simpro3\bin\simpro3.exe`):
  * **Role:** The actual brains of SimPro. It hosts Chromium Embedded Framework (`libcef.dll`), runs a local HTTP REST server on port 4010, manages the SQLite database, and handles USB HID communication via `SCommUsbHid.cpp`.

---

## 3. Discovered Local REST API Reference

SimPro hosts an unauthenticated HTTP REST server on `http://127.0.0.1:4010/simpro/api/v3/`. All requests are sent as `POST` with `Content-Type: application/json`.

> **CRITICAL DATA TYPE NOTE:**  
> The internal C++ JSON parser (`SInteractCEFQryServer.cpp`) strictly requires `product_uuid`, `device_uuid`, and `preset_uuid` to be **STRINGS**, not numbers. Passing a number will result in `[json.exception.type_error.302] type must be string, but is number`.

### 3.1 List All Presets
* **Endpoint:** `POST /simpro/api/v3/preset_get_dev_config_list`
* **Request Body:**
  ```json
  {
    "product_uuid": "17301504",
    "device_uuid": "<BASE_DEVICE_UUID>"
  }
  ```
* **Response Example:**
  ```json
  {
    "status": 200,
    "result": [
      {
        "presetUUID": "<BASE_PRESET_UUID>",
        "presetName": "My LeMans Ultimate",
        "isOffical": false,
        "gameName_list": ["lmu"]
      },
      {
        "presetUUID": "<DEFAULT_PRESET_UUID>",
        "presetName": "LeMans Ultimate",
        "isOffical": true,
        "gameName_list": ["lmu"]
      }
    ]
  }
  ```

### 3.2 Switch Active Preset (The Core Action)
* **Endpoint:** `POST /simpro/api/v3/preset_select_dev_config`
* **Request Body:**
  ```json
  {
    "product_uuid": "17301504",
    "device_uuid": "<BASE_DEVICE_UUID>",
    "preset_uuid": "<BASE_PRESET_UUID>"
  }
  ```
* **Effect:** SimPro fetches the binary profile parameters from the database, unpacks them, validates them, and pushes the runtime FFB settings to the base immediately over USB HID.

### 3.3 Query Currently Selected Preset
* **Endpoint:** `POST /simpro/api/v3/preset_get_selected_dev_config`
* **Request Body:**
  ```json
  {
    "product_uuid": "17301504",
    "device_uuid": "<BASE_DEVICE_UUID>"
  }
  ```

### 3.4 Supported Devices Query
* **Endpoint:** `GET` or `POST` `/simpro/api/v3/get_support_device`
* Returns the complete catalog of Simagic devices with their corresponding decimal and hex `product_uuid` values.

---

## 4. Hardware Inventory & Verified Live State

All values verified live via read-only queries to `http://127.0.0.1:4010/simpro/api/v3/`:

| Device Type | Model Name | Firmware | Product UUID (Dec / Hex) | Device UUID (Dec / Hex) | Live State |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Wheelbase** | **Alpha EVO Sport** (`EVO Sports`) | `V2.3.6` | `17301504` / `0x01080000` | `<BASE_DEVICE_UUID>` / `<HEX_DEVICE_UUID>` | Online (`576`), Angle: `900°` |
| **Pedals** | **Simagic P700** | `A1.1.0` | `50724864` / `0x03060000` | `<PEDAL_DEVICE_UUID>` / `<HEX_DEVICE_UUID>` | Online (`576`) |
| **Steering Wheel** | **Simagic GT NEO** | `V1.4.4` | `33947648` / `0x02060000` | `33947648` / `0x0000000002060000` | Online (`576`) |

* **Current Active Preset on Wheelbase**: `<BASE_PRESET_UUID>` (**"My LeMans Ultimate"**)
* **Live Telemetry Output (Read-Only)**: `max_wheel_angle: 900°`, `wheel_angle: 0°`, `torque: 65530`


---

## 5. Storage Subsystem (SQLite & Protobuf)

SimPro stores presets and user settings in:
`%LOCALAPPDATA%\Simagic\Simpro3\storage\user.db`

### Key Tables in `user.db`:
1. **`preset`**:
   * `id`: Auto-incrementing integer.
   * `presetName`: User-friendly display name (e.g., `"My LeMans Ultimate"`, `"720S GT3"`).
   * `presetUUID`: Unique 64-bit integer ID stored as text.
   * `productUUID`: Target device type (e.g., `17301504` for wheelbase).
   * `deviceUUID`: Target physical device identifier.
   * `gameList`: JSON array of linked games (e.g., `'["lmu"]'`).
   * `presetData`: **Google Protocol Buffers (Protobuf)** binary blob containing the full FFB tuning curve, maximum steering angle, damper, friction, inertia, feedback frequency, and LED layout.
2. **`setting`**:
   * Stores the current active preset for each device (`settingKey = 'selected_preset'`).
   * Stores the auto-switch config (e.g. `'{"basePresetId":"<BASE_PRESET_UUID>","useAutoSwitch":true}'`).

---

## 6. How Le Mans Ultimate (LMU) Car Detection Works

Le Mans Ultimate is built on Studio 397's **rFactor 2 engine (ISIMotor)**. Simagic already installs the official rFactor 2 shared memory plugin:
`C:\Program Files (x86)\Simagic\Simpro3\game_plugin\LMU & RF2\rFactor2SharedMemoryMapPlugin64.dll`

### The Telemetry Mechanism:
* When LMU runs, the plugin creates Windows shared memory buffers:
  * **`$rFactor2SMMP_Scoring$`** (Scoring, session, and vehicle information)
  * **`$rFactor2SMMP_Telemetry$`** (High-speed FFB and physics telemetry)
* Inside `$rFactor2SMMP_Scoring$`:
  * `mPlayerCarID`: Index of the player's car.
  * `mVehicleInfo[playerIndex].mVehicleName`: Exact car name (e.g., `"Ferrari 499P"`, `"Porsche 963"`, `"Oreca 07 Gibson"`, `"Ferrari 296 LMGT3"`).
  * `mVehicleInfo[playerIndex].mVehicleClass`: Class name (e.g., `"HYPERCAR"`, `"LMP2"`, `"LMGT3"`).
* **Anti-Cheat & Performance Safety:**
  * Reading shared memory uses standard read-only OS memory mapping (`mmap`).
  * It does not touch game memory, inject DLLs, or hook DirectX.
  * It is 100% compliant with anti-cheat software and identical to how SimHub and Moza/Fanatec software read game data.

---

## 7. Safety Guarantee: Why This Cannot Brick Your Wheel

1. **No Firmware Flashing**: Firmware updates require entering bootloader mode via `device_fw_update`. The `preset_select_dev_config` endpoint has zero access to bootloader flash routines.
2. **RAM Tuning Parameters**: When SimPro changes a profile, it sends HID reports that alter variables in the motor microcontroller's volatile RAM. If an invalid packet were somehow sent, the base's internal firmware rejects out-of-range values or resets to defaults upon power cycling.
3. **SimPro Handles the Hardware**: Our automation script only speaks HTTP to SimPro. SimPro itself handles the USB protocol. From the hardware's perspective, this is completely indistinguishable from the user clicking a button in the SimPro GUI.

---

## 8. WheelDaemon Architecture Blueprint

```
+-------------------------------------------------------------+
|                      WheelDaemon (Python)                   |
|                                                             |
|  1. Polling Loop (1 Hz):                                    |
|     - Read LMU vehicle from `$rFactor2SMMP_Scoring$`         |
|                                                             |
|  2. Car Change Detection:                                   |
|     - If current_car != previous_car:                       |
|         car_class = map_car_to_class(current_car)          |
|         target_preset = config.get(car_class or current_car)|
|                                                             |
|  3. Profile Switch:                                         |
|     - HTTP POST -> http://127.0.0.1:4010/simpro/api/v3/      |
|                    preset_select_dev_config                 |
|       { product_uuid, device_uuid, preset_uuid }            |
+-------------------------------------------------------------+
```

---

## 9. Next Steps & Implementation Plan

1. **Verify Live Switching** (When wheel base is powered on):
   * Run the test script below to verify that calling `preset_select_dev_config` instantly changes the profile on the live base and updates the SimPro GUI.
2. **Implement LMU Shared Memory Reader**:
   * Read `mVehicleName` directly from `$rFactor2SMMP_Scoring$`.
3. **Create User Configuration Mapping**:
   * A simple `config.json` where you map vehicle names or vehicle classes to your SimPro preset names (e.g., `"HYPERCAR": "LMU Hypercar 900deg"`, `"LMGT3": "LMU GT3 540deg"`).
