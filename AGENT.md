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

---

## 3. Hardware Identifiers & Environment Topology

### Physical Hardware on Host System:
| Device | Product Name | Product UUID (Dec / Hex) | Device UUID (Dec / Hex) | Firmware | Role |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Base** | Alpha EVO Sport | `'17301504'` (`0x01080000`) | `'<BASE_DEVICE_UUID>'` (`<HEX_DEVICE_UUID>`) | `V2.3.6` | Direct-drive FFB & CAN-FD Master |
| **Wheel** | GT NEO | `'33947648'` (`0x02060000`) | `'33947648'` (`0x02060000`) | `V1.4.4` | CAN-FD Slave (Buttons, Clutch, LEDs) |
| **Pedals** | P700 | `'50724864'` (`0x03060000`) | `'<PEDAL_DEVICE_UUID>'` (`<HEX_DEVICE_UUID>`) | `A1.1.0` | Load cell / Hall sensor pedal curves |

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
│   └── create_windows_shortcuts.py        # Desktop / Start Menu shortcut generator
│
├── assets/                                # Application icons
│   ├── icon.ico                           # Multi-resolution Windows icon
│   └── icon.png                           # 256x256 RGBA application icon
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
* **Never run blocking interactive `git push` commands** in background subshells. Windows Git Credential Manager requires an interactive user terminal to render browser OAuth dialogs.
* Stage (`git add .`) and commit (`git commit -m "..."`) locally, then instruct the user to run `git push -u origin main` in their interactive terminal.

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

## 6. Vehicle Mapping Matrix (Quick Reference)

| In-Game Vehicle Class / Token | GT NEO Profile Name | SimPro Preset UUID |
| :--- | :--- | :--- |
| **Ferrari 296 GT3** (`296`, `AFCO`) | `GT3 296` | `<WHEEL_PRESET_UUID_296>` |
| **McLaren 720S GT3 Evo** (`720S`, `GARA`, `GCHAL`) | `GT3 720S` | `<WHEEL_PRESET_UUID_720S>` |
| **Porsche 911 GT3 R** (`911`, `MANT`) | `GT3 911` | `<WHEEL_PRESET_UUID_911>` |
| **BMW M4 GT3** (`M4`, `WRT`) | `GT3 M4` | `<WHEEL_PRESET_UUID_M4>` |
| **Ford Mustang GT3** (`MUSTANG`, `PROT`) | `GT3 Mustang` | `<WHEEL_PRESET_UUID_MUSTANG>` |
| **Lexus RC F GT3** (`LEXUS`, `RCF`, `AKKO`) | `GT3 RCF` | `<WHEEL_PRESET_UUID_RCF>` |
| **Corvette Z06 GT3.R** (`CORVETTE`, `Z06`, `TFSP`) | `GT3 Vette` | `<WHEEL_PRESET_UUID_VETTE>` |
| **Aston Martin Vantage GTE** (`DSTATI`, `AMR GTE`) | `GTE AMR` | `<WHEEL_PRESET_UUID_AMR>` |
| **Cadillac V-Series.R** (`CADILLAC`, `V-SERIES`) | `HYP Cadillac` | `<WHEEL_PRESET_UUID_CADILLAC>` |
| **Peugeot 9X8** (`PEUGEOT`, `9X8`) | `HYP Peugeot` | `<WHEEL_PRESET_UUID_PEUGEOT>` |
| **Aston Martin Valkyrie LMH** (`VALKYRIE`, `007_`) | `HYP Valkyrie` | `<WHEEL_PRESET_UUID_VALKYRIE>` |
| **Oreca 07 LMP2** (`ORECA`, `07_LMP2`, `VECTOR`) | `LM P2` | `<WHEEL_PRESET_UUID_LMP2>` |
| **Ginetta G61-LT-P325 LMP3** (`GINETTA`, `G61`, `LMP3`) | `LMP3 Ginetta` | `<WHEEL_PRESET_UUID_GINETTA>` |
| **Default Fallback** | `My GT Neo Default` | `<WHEEL_PRESET_UUID_DEFAULT>` |

*Wheelbase profile targets **`My LeMans Ultimate`** (`<BASE_PRESET_UUID>`).*
