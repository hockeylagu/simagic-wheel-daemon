# 🏎️ Simagic Wheel Daemon - Agent Guidelines (AGENT.md)

This document establishes the architectural standards, domain rules, safety constraints, hardware invariants, and operational workflows for AI agents working in this repository.

---

## 1. Project Purpose & High-Level Mission

**simagic-wheel-daemon** is a standalone, lightweight automation daemon for the **Simagic direct-drive ecosystem** (Alpha EVO Sport wheelbase, GT NEO steering wheel, P700 pedals) paired with **Le Mans Ultimate (LMU)**.

### Primary Goals:
1. **Goal 1 (Automatic Profile Switching)**: Automatically detect when the driver loads into any vehicle in LMU, and immediately switch the active profile on both the **Wheelbase** (FFB, rotation angle, damping) and the **GT NEO Steering Wheel** (button bindings, clutch bite point, LED themes).
2. **Goal 2 (Custom CAN-FD Rev Lights & Telemetry LEDs)**: Accurately match in-game tachometer RPM, shift points, pit limiter, and traction control (TC) alerts on the GT NEO's rev LEDs running **100% over CAN-FD** through the quick release pogo pins—without requiring a Maglink USB cable or third-party software like SimHub.

---

## 2. Non-Negotiable Invariants & Safety Constraints

When writing code, refactoring, or modifying configurations, agents must adhere strictly to these core rules:

### 🛡️ A. Absolute Hardware Safety (ZERO BRICKING RISK)
* **NEVER attempt raw USB HID injection, bootloader commands, or firmware flashing.**
* Simagic hardware is expensive and delicate. We do **not** flash microcontrollers, rewrite EEPROMs, or bypass SimPro Manager.
* **All communication must go through SimPro Manager v3's official local REST API** (`http://127.0.0.1:4010/simpro/api/v3/`).
* SimPro Manager's local C++ server validates all JSON payloads (`SInteractCEFQryServer.cpp`) and updates volatile RAM runtime parameters identically to a user clicking buttons in the official GUI.

### 🔌 B. Native CAN-FD Operation (No Maglink USB Cable Required)
* The user's GT NEO wheel connects to the Alpha EVO Sport wheelbase via the **quick release pogo pins** over **CAN-FD** (`active_connect_mode: [4]`).
* Do not assume or require a Maglink USB cable. The daemon operates wirelessly through the wheelbase CAN-FD bridge.

### 🚫 C. Zero SimHub Dependency
* SimHub is **not** an option. WheelDaemon must remain 100% standalone, lightweight, and self-contained.
* Do not incorporate SimHub plugins, DLLs, or runtime requirements.

### 🔒 D. 100% Anti-Cheat Compliant (Le Mans Ultimate)
* LMU runs Easy Anti-Cheat (EAC).
* **NEVER hook game memory, inject DLLs, or inspect private memory spaces.**
* Read game states exclusively via:
  1. LMU's official embedded HTTP REST API (`http://localhost:6397/navigation/state` & `/rest/watch/standings`).
  2. rFactor 2 shared memory mapped file (`$rFactor2SMMP_Scoring$`) using standard read-only Win32 memory mapping.

### 📜 E. REST API Type Strictness
* SimPro's C++ JSON parser strictly enforces that `product_uuid`, `device_uuid`, and `preset_uuid` must be **strings**, not numbers. Passing numeric integers triggers `type_error.302`. Always pass them as `str(uuid)`.

### 🛡️ F. Strict Local Workspace Isolation (`local/` Directory)
* The `local/` folder is strictly private and gitignored (`local/`, `/local/`, `local/**`).
* **NEVER stage, add, or commit files from `local/` to Git.**
* `git add -f local/` is strictly prohibited.
* Never document, describe, or list the contents of the `local/` folder in tracked repository documentation.



---

## 3. Hardware Identifiers & Environment Topology

### Physical Hardware Topology:
| Device | Product Name | Product UUID (Dec / Hex) | Device UUID | Firmware | Role |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Base** | Alpha EVO Sport | `'17301504'` (`0x01080000`) | `<BASE_DEVICE_UUID>` | `V2.x` | Direct-drive FFB & CAN-FD Master |
| **Wheel** | GT NEO | `'33947648'` (`0x02060000`) | `'33947648'` | `V1.x` | CAN-FD Slave (Buttons, Clutch, LEDs) |
| **Pedals** | P700 | `'50724864'` (`0x03060000`) | `<PEDAL_DEVICE_UUID>` | `A1.x` | Load cell / Hall sensor pedal curves |


### Software Endpoints:
* **SimPro Manager v3 Local REST Server**: `http://127.0.0.1:4010/simpro/api/v3/`
* **SimPro SQLite User Database**: `%LOCALAPPDATA%\Simagic\Simpro3\storage\user.db`
* **LMU Embedded REST API**: `http://localhost:6397`
* **LMU Shared Memory Buffer**: Win32 mapped file `$rFactor2SMMP_Scoring$`

---

## 4. Directory Structure & Code Organization

```
WheelDeamon/
├── docs/                                  # Deep technical documentation
│   ├── CODE_MAP.md                        # File index, flow tracing, and architecture
│   ├── SIMAGIC_RESEARCH_FINDINGS.md       # SimPro REST API protocol and IPC discovery
│   ├── SIMAGIC_TELEMETRY_AND_LEDS.md      # Telemetry channels, RPM calculations & LED schemas
│   ├── LMU_API_AND_VEHICLE_MAPPING.md     # LMU embedded REST endpoints & vehicle tokens
│   └── ROADMAP_AND_ARCHITECTURE.md        # Technical roadmap (Profile Switching & CAN-FD LEDs)
│
├── src/simagic_daemon/                    # Core Python package
│   ├── __init__.py                        # Version and package exports
│   ├── __main__.py                        # CLI entrypoint for python -m simagic_daemon
│   ├── daemon.py                          # SimagicWheelDaemon background service
│   ├── tray.py                            # Windows System Tray app (pystray)
│   ├── notifications.py                   # Non-blocking Windows Toast notifications
│   ├── process_utils.py                   # Process monitor for SimPro & LMU
│   ├── simagic_client.py                  # HTTP client for SimPro Manager REST API
│   ├── vehicle_mapping.py                 # LMU vehicle resolver & GT NEO preset map
│   └── lmu_reader.py                      # Telemetry ingestion (REST API + Shared Memory)
│
├── tools/                                 # Standalone CLI diagnostic utilities
│   ├── test_simagic_connection.py         # Hardware discovery & SimPro REST API tester
│   ├── test_lmu_connection.py             # LMU telemetry & vehicle resolver tester
│   ├── view_logs.py                       # Inspect & follow daemon debug logs
│   ├── create_windows_shortcuts.py        # Desktop / Start Menu shortcut generator
│   └── update_icon.py                     # Generates app icons from authentic wheel image
│
├── assets/                                # Application icons
│   ├── icon.ico                           # Multi-resolution Windows icon (16px to 256px)
│   └── icon.png                           # 512x512 RGBA application icon
│
├── local/                                 # [GITIGNORED] Local private directory (never committed)
├── logs/                                  # [GITIGNORED] Rotating log outputs (daemon.log)
│
├── SimagicWheelDaemon.bat                 # Windows batch launcher (Console mode)
├── SimagicWheelDaemon.vbs                 # Windows silent VBS launcher (System Tray mode)
│
├── AGENT.md                               # Agent guidelines and architectural standards
├── CODE_MAP.md                            # Code map link / quick reference
├── LICENSE                                # MIT License
├── pyproject.toml                         # Standard PEP 517/621 packaging metadata
└── README.md                              # User-facing setup & usage documentation
```

---

## 5. Coding & Development Standards

### A. Python Standards
* Use standard library wherever feasible (`urllib.request`, `sqlite3`, `mmap`, `json`, `argparse`, `logging`).
* Python 3.10+ compatibility with explicit type hints (`typing.Optional`, `typing.Dict`, `typing.List`, `typing.Tuple`).
* Avoid adding heavy third-party dependencies unless strictly justified.

### B. Windows Console Encoding
* The host OS is Windows. Default PowerShell console encoding may be `cp1252`.
* Always include `if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")` in entrypoints and tools to prevent `UnicodeEncodeError`.

### C. Git Execution & Authentication
* **Configured GitHub Account**: This repository is explicitly bound to the `hockeylagu` GitHub account (`https://hockeylagu@github.com/hockeylagu/simagic-wheel-daemon.git` with `credential.https://github.com.username hockeylagu`).
* **Keep `local/` strictly untracked**: Ensure `local/` is always ignored in `.gitignore`. Never run `git add -f local/` or commit any file residing in `local/`.



### D. Testing & Verification
* Whenever modifying SimPro client logic, run:
  ```bash
  python tools/test_simagic_connection.py
  ```
* Whenever modifying LMU vehicle mapping, run:
  ```bash
  python tools/test_lmu_connection.py
  ```
* Test daemon poll iterations with:
  ```bash
  python -m simagic_daemon --dry-run --once
  ```

---

## 6. Vehicle Mapping Architecture (Quick Reference)

The daemon resolves raw in-game vehicle identifiers (`vehFile`, `carType`, `model`) deterministically to friendly vehicle names and corresponding profile presets.

* **Wheelbase Profile**: Automatically activates the configured wheelbase direct-drive profile.
* **GT NEO Steering Wheel**: Automatically maps car classes (LMGT3, Hypercar, LMP2, GTE) to custom steering wheel profiles (buttons, rev light LED thresholds, bite-point).
* **Discovering User Presets**: User presets can be inspected and verified dynamically using:
  ```bash
  python tools/test_simagic_connection.py
  ```

