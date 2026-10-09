# 🗺️ Code Map: Where Things Live and How They Flow

A comprehensive architectural index for developers and agents: find the right file immediately and understand the data flows through **simagic-wheel-daemon**.

`AGENT.md` holds the invariants and safety rules; this document maps the **routes through the code**.

---

## 1. High-Level Data Flow Architecture

The daemon operates as a non-intrusive bridge between **Le Mans Ultimate (LMU)** and **SimPro Manager v3**, executing profile switches and LED configuration over native **CAN-FD**:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Le Mans Ultimate (LMU)                          │
│  • Embedded REST API (:6397/navigation/state, /rest/watch/standings)   │
│  • Win32 Shared Memory Map ($rFactor2SMMP_Scoring$)                    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Stage 1: Ingest (Read-only polling)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│               src/simagic_daemon/lmu_reader.py (LMUReader)             │
│  Extracts vehicle token (e.g. '296_GT3.veh', 'Cadillac V-Series.R')    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Stage 2: Vehicle Token String
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│          src/simagic_daemon/vehicle_mapping.py (Resolver)              │
│  Matches vehicle token to friendly name & SimPro Preset UUID           │
│  Output: ('Ferrari 296 GT3', '<TARGET_PRESET_UUID>', 'GT3 296')        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Stage 3: Target Preset UUID
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│          src/simagic_daemon/simagic_client.py (SimagicClient)          │
│  Sends JSON POST to SimPro Manager local REST API (Port 4010)          │
│  Calls: preset_select_dev_config, preset_set_dev_config                │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Stage 4: Official SimPro C++ Engine
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   SimPro Manager v3 (C++ Core Daemon)                  │
│  SInteractCEFQryServer -> SCommUsbHid::writeOutReportCanfdSync()       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Stage 5: Physical Hardware
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             Simagic Alpha EVO Sport Direct-Drive Base                  │
│                          │                                             │
│                          ▼ (CAN-FD through Quick Release Pogo Pins)    │
│                 GT NEO Steering Wheel & P700 Pedals                    │
│      Profile activated: FFB, buttons, bite-point & rev lights.         │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Directory & Module Index

### 📦 Core Package (`src/simagic_daemon/`)

| File | Primary Classes / Functions | Responsibility |
| :--- | :--- | :--- |
| **[`daemon.py`](file:///c:/Documents/WheelDeamon/src/simagic_daemon/daemon.py)** | `SimagicWheelDaemon`, `main()` | Main execution service. Houses the polling loop, signal handlers (`SIGINT`/`SIGTERM`), state diffing, and CLI options (`--dry-run`, `--once`, `--poll-interval`, `--revert-on-exit`). |
| **[`simagic_client.py`](file:///c:/Documents/WheelDeamon/src/simagic_daemon/simagic_client.py)** | `SimagicClient`, `call_simpro_api()`, `switch_preset()`, `list_presets_from_db()` | High-level HTTP client interfacing with SimPro Manager's local REST API on `http://127.0.0.1:4010/simpro/api/v3/`. Also provides read-only SQLite inspection of `user.db`. |
| **[`catalog_sync.py`](../src/simagic_daemon/catalog_sync.py)** | `refresh_catalog()`, `merge_rows()` | Adds unknown vehicle IDs from `GET /rest/sessions/getAllVehicles` to the vehicle catalog (append-only, atomic write). The daemon runs it in the background when LMU starts and when an unknown car is loaded. |
| **[`capture.py`](../src/simagic_daemon/capture.py)** | `run_capture()`, `iter_capture()` | Records raw LMU REST documents and the rF2 scoring buffer (on change only) for offline verification and replay. |
| **[`config.py`](../src/simagic_daemon/config.py)** | `load_config()`, `get_config_value()` | Locates and loads the private `user_presets.json` (hardware & preset UUIDs). |
| **[`vehicle_mapping.py`](file:///c:/Documents/WheelDeamon/src/simagic_daemon/vehicle_mapping.py)** | `resolve_vehicle_to_preset()`, `PRESET_MAP_GT_NEO` | Pure deterministic token resolution engine. Maps raw vehicle identifiers (`vehFile`, `carType`, `model`) to GT NEO and Base preset UUIDs. |
| **[`lmu_reader.py`](file:///c:/Documents/WheelDeamon/src/simagic_daemon/lmu_reader.py)** | `LMUReader` | Telemetry & session reader. Probes LMU's embedded REST server (`localhost:6397`) and rFactor 2 shared memory (`$rFactor2SMMP_Scoring$`). |
| **[`tray.py`](file:///c:/Documents/WheelDeamon/src/simagic_daemon/tray.py)** | `SimagicTrayApp`, `main()` | Windows System Tray application. Hosts the daemon in a background thread, shows real-time vehicle/profile indicators in the taskbar, and provides a context menu with actions (test notifications, launch SimPro, exit). |
| **[`notifications.py`](file:///c:/Documents/WheelDeamon/src/simagic_daemon/notifications.py)** | `send_windows_notification()` | Native Windows Toast notifications. Dispatches non-blocking WinRT toasts via PowerShell with debouncing to prevent spam. |
| **[`logger.py`](file:///c:/Documents/WheelDeamon/src/simagic_daemon/logger.py)** | `setup_logging()`, `open_log_file()` | Centralized rotating file logger (5 MB with 3 backups) and console stream handler. |
| **[`process_utils.py`](file:///c:/Documents/WheelDeamon/src/simagic_daemon/process_utils.py)** | `is_simpro_running()`, `is_lmu_running()`, `launch_simpro()` | Windows process watchdog for `simpro3.exe` and `lemansultimate.exe`. Auto-launches SimPro when requested. |
| **[`__main__.py`](file:///c:/Documents/WheelDeamon/src/simagic_daemon/__main__.py)** | - | Package executable wrapper enabling `python -m simagic_daemon`. |
| **[`__init__.py`](file:///c:/Documents/WheelDeamon/src/simagic_daemon/__init__.py)** | `__version__`, exports | Public module export boundary and package metadata. |

---

### 🔧 Diagnostic & Logging Tools (`tools/`)

| File | Command | Purpose |
| :--- | :--- | :--- |
| **[`view_logs.py`](file:///c:/Documents/WheelDeamon/tools/view_logs.py)** | `python tools/view_logs.py` | Inspects recent debug logs, tails live log stream (`--follow`), or opens in Notepad (`--open`). |
| **[`create_windows_shortcuts.py`](file:///c:/Documents/WheelDeamon/tools/create_windows_shortcuts.py)** | `python tools/create_windows_shortcuts.py` | Generates Desktop, Start Menu, and Startup `.lnk` shortcuts configured with the GT Neo icon. |
| **[`update_icon.py`](file:///c:/Documents/WheelDeamon/tools/update_icon.py)** | `python tools/update_icon.py` | Converts source wheel images into centered 512x512 PNG and multi-resolution Windows ICO. |
| **[`test_simagic_connection.py`](file:///c:/Documents/WheelDeamon/tools/test_simagic_connection.py)** | `python tools/test_simagic_connection.py` | Standalone CLI diagnostic. Verifies SimPro REST API status (port 4010), catalogs all connected devices (Base, Wheel, Pedals) with firmware versions, and reads active presets. |
| **[`validate_vehicle_mapping.py`](../tools/validate_vehicle_mapping.py)** | `python tools/validate_vehicle_mapping.py` | Resolves every real LMU vehicle ID in the vehicle catalog four ways (catalog, ID + class + make, ID + class, ID only) and reports which car/profile each picks versus the truth. |
| **[`setup_user_presets.py`](../tools/setup_user_presets.py)** | `python tools/setup_user_presets.py` | Builds `user_presets.json` offline from SimPro's `user.db`: device UUIDs, the LMU wheelbase profile, and each GT NEO key matched to the LMU-tagged profile of the same name. Keeps existing values unless `--overwrite`. |
| **[`generate_vehicle_catalog.py`](../tools/generate_vehicle_catalog.py)** | `python tools/generate_vehicle_catalog.py` | With LMU running, adds every installed car's vehicle ID from `GET /rest/sessions/getAllVehicles` to the vehicle catalog (`lmu_vehicle_catalog.json`, same search locations as `user_presets.json`). |
| **[`replay_capture.py`](../tools/replay_capture.py)** | `python tools/replay_capture.py local/captures/<session>` | Replays raw LMU data recorded with `simagic-daemon --capture` through the current parsers and vehicle mapping; flags snapshots that now parse differently. |
| **[`test_lmu_connection.py`](file:///c:/Documents/WheelDeamon/tools/test_lmu_connection.py)** | `python tools/test_lmu_connection.py` | Standalone CLI diagnostic. Verifies LMU REST API and shared memory connectivity, testing vehicle resolution against a simulated grid. |

---

### 🛡️ Local Workspace & Assets

| Path | Tracking Status | Responsibility |
| :--- | :--- | :--- |
| **[`local/`](file:///c:/Documents/WheelDeamon/local/)** | **Strictly Gitignored** | Local private folder. Never tracked or committed. |

| **[`logs/`](file:///c:/Documents/WheelDeamon/logs/)** | **Strictly Gitignored** | Daemon runtime rotating log files (`daemon.log`). |
| **[`assets/`](file:///c:/Documents/WheelDeamon/assets/)** | Tracked in Git | Application icons (`icon.png`, `icon.ico`) featuring the authentic GT Neo butterfly wheel. |


---

### 📚 Technical Documentation (`docs/`)

| File | Topic & Contents |
| :--- | :--- |
| **[`SIMAGIC_RESEARCH_FINDINGS.md`](file:///c:/Documents/WheelDeamon/docs/SIMAGIC_RESEARCH_FINDINGS.md)** | SimPro Manager v3 reverse engineering, CEF architecture, HTTP REST server (`SInteractCEFQryServer.cpp`), SQLite storage schema, and CAN-FD USB transport layer. |
| **[`SIMAGIC_TELEMETRY_AND_LEDS.md`](file:///c:/Documents/WheelDeamon/docs/SIMAGIC_TELEMETRY_AND_LEDS.md)** | Technical specification of telemetry items, per-car RPM threshold scaling, rev light configuration schemas, and shift alert payloads over CAN-FD. |
| **[`LMU_API_AND_VEHICLE_MAPPING.md`](file:///c:/Documents/WheelDeamon/docs/LMU_API_AND_VEHICLE_MAPPING.md)** | Le Mans Ultimate embedded HTTP REST API reference (`:6397`) and token normalization logic for LMGT3, Hypercar, LMP2, and GTE grids. |
| **[`ROADMAP_AND_ARCHITECTURE.md`](file:///c:/Documents/WheelDeamon/docs/ROADMAP_AND_ARCHITECTURE.md)** | Original phase plan. Phase 2 (CAN-FD Dynamic LEDs) is now a separate project; only profile switching is in scope here. |

---

## 3. SimPro REST API Endpoints Reference

Base URL: `http://127.0.0.1:4010/simpro/api/v3`

| Endpoint | Method | Key Parameters | Description |
| :--- | :--- | :--- | :--- |
| `get_support_device` | POST | `{}` | Heartbeat endpoint. Confirms API server is responsive. |
| `get_device_list` | POST | `{}` | Returns all connected physical hardware devices, product UUIDs, device UUIDs, and firmware versions. |
| `preset_get_selected_dev_config` | POST | `{"product_uuid": str, "device_uuid": str}` | Returns the currently active profile UUID on the specified device. |
| `preset_select_dev_config` | POST | `{"product_uuid": str, "device_uuid": str, "preset_uuid": str}` | **Switches active preset.** 100% safe official C++ method. |
| `preset_get_dev_config_list` | POST | `{"product_uuid": str, "device_uuid": str}` | Lists all saved user presets for a device. |
| `preset_get_dev_config` | POST | `{"product_uuid": str, "device_uuid": str, "preset_uuid": str}` | Fetches full configuration JSON (LEDs, FFB, button curves). |
| `preset_set_dev_config` | POST | `{"product_uuid": str, "device_uuid": str, "config": {...}}` | Updates runtime device configuration in volatile memory. |

> ⚠️ **Strict Type Requirement**: All UUID parameters (`product_uuid`, `device_uuid`, `preset_uuid`) MUST be strings (e.g. `"17301504"`). Passing numbers causes `type_error.302`.

---

## 4. Common Recipes & Development Workflows

### Recipe A: Adding a New Vehicle or Profile
1. Create and customize the profile in SimPro Manager v3 GUI, tag it LMU and name it after the key's label (e.g. `HYP 499P`).
2. Run `python tools/setup_user_presets.py` to add it to `user_presets.json`
   (or put the preset UUID under its key in `"presets"` by hand, e.g. `"HYP_499P": "<uuid>"`).
3. If LMU added cars or liveries, refresh the catalog: `python tools/generate_vehicle_catalog.py`.
   Every car has its own key; unconfigured keys fall back along `PRESET_FALLBACKS` (ending at `DEFAULT`).
4. For a car that is not yet recognised, add a `VehicleRule` to `VEHICLE_RULES` in
   `src/simagic_daemon/vehicle_mapping.py` (class, model tokens, team tokens) plus its key in
   `PRESET_MAP_GT_NEO`, `PRESET_LABELS` and, optionally, `PRESET_FALLBACKS`.
5. Test with `python tools/test_lmu_connection.py`.

### Where `user_presets.json` Is Loaded From
`src/simagic_daemon/config.py` uses the first file found in:
1. The path in the `SIMAGIC_DAEMON_CONFIG` environment variable
2. `local/user_presets.json` in the current working directory
3. `local/user_presets.json` in the repository root (editable installs)
4. `%APPDATA%\SimagicWheelDaemon\user_presets.json` (regular `pip install`)

### Recipe B: Testing Daemon Detection Without LMU Running
Run the daemon in dry-run single-step mode:
```bash
python -m simagic_daemon --dry-run --once
```

### Recipe C: Running the Daemon in Background
```bash
python -m simagic_daemon --poll-interval 1.0 --revert-on-exit
```

---

## 5. Known Pitfalls & Anti-Patterns

| Anti-Pattern | Why It Breaks | Correct Pattern |
| :--- | :--- | :--- |
| Passing integers for UUIDs in API calls | Triggers `type_error.302` in SimPro C++ parser | Always stringify: `str(uuid)` |
| Direct USB HID communication | High risk of bricking firmware / EEPROM corruption | Always route via SimPro REST API |
| Polling LMU memory with aggressive rates | Wastes CPU cycles when in menus | Use 1.0s interval when idle / loading |
| Relying on SimHub | Violates project goal of zero SimHub dependency | Keep daemon 100% standalone |
| Unescaped UTF-8 in Windows console | Causes `UnicodeEncodeError` on `cp1252` terminals | Use `sys.stdout.reconfigure(encoding="utf-8")` |
