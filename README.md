# 🏎️ simagic-wheel-daemon

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](https://www.microsoft.com/windows)
[![CAN-FD Native](https://img.shields.io/badge/CAN--FD-Quick%20Release-brightgreen.svg)]()

**simagic-wheel-daemon** is a lightweight, standalone automation daemon for **Simagic** direct-drive ecosystems (Alpha EVO Sport wheelbase, GT NEO steering wheel, P700 pedals). It provides automatic, per-vehicle profile switching and accurate RPM rev light calibration in **Le Mans Ultimate (LMU)** running **100% over CAN-FD** through the Simagic Quick Release—without requiring a Maglink USB cable or third-party tools like SimHub.

---

## 🌟 Key Features

* **⚡ Automatic Per-Vehicle Profile Switching:** Automatically detects when you load into any car in Le Mans Ultimate and switches the active profile on both your **Wheelbase** (FFB, rotation angle, damping) and **GT NEO Steering Wheel** (button mappings, clutch bite point, LED themes, rev lights).
* **🏎️ CAN-FD Quick Release Operation:** Communicates through the quick release pogo pins via native CAN-FD. No Maglink USB cable required; keep your cockpit wireless and clutter-free.
* **🛡️ 100% Safe (Zero Bricking Risk):** Interacts exclusively with SimPro Manager's official local REST API (`http://127.0.0.1:4010/simpro/api/v3/`). Never touches microcontroller flash or bootloaders; all adjustments update volatile RAM runtime parameters identically to official GUI clicks.
* **🔒 Anti-Cheat Compliant:** Reads LMU game states using LMU's embedded HTTP REST API (`http://localhost:6397`) and official rFactor 2 shared memory (`$rFactor2SMMP_Scoring$`). Zero DLL injection, zero memory hooks.
* **🚫 SimHub-Free Standalone Engine:** Operates completely independently without SimHub or third-party plugin bloat.

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Le Mans Ultimate (LMU)                          │
│   • Embedded REST API (http://localhost:6397/navigation/state)         │
│   • rFactor 2 Shared Memory Map ($rFactor2SMMP_Scoring$)               │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼ (HTTP GET / Read-only Win32 mmap)
┌────────────────────────────────────────────────────────────────────────┐
│                 simagic-wheel-daemon (Python Daemon)                   │
│   1. Reads active car (e.g. 296_GT3.veh, Oreca 07, Cadillac V-Series)   │
│   2. Resolves vehicle identity via vehicle_mapping.py                  │
│   3. Sends HTTP POST to SimPro Manager local REST server               │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼ (HTTP POST to http://127.0.0.1:4010/simpro/api/v3/)
┌────────────────────────────────────────────────────────────────────────┐
│                          SimPro Manager v3                             │
│   • preset_select_dev_config: Selects wheelbase & wheel profiles       │
│   • Packages frames via SCommUsbHid::writeOutReportCanfdSync()         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼ (USB HID -> CAN-FD Quick Release Pogo Pins)
┌────────────────────────────────────────────────────────────────────────┐
│          Alpha EVO Sport Base   ──►   GT NEO Steering Wheel            │
│   Profile activated instantly. Rev lights match in-game tachometer.    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Repository Structure

Adhering to standard Python packaging best practices:

```
simagic-wheel-daemon/
├── docs/                                  # In-depth technical specifications & research
│   ├── SIMAGIC_RESEARCH_FINDINGS.md       # SimPro reverse engineering & REST API protocol
│   ├── SIMAGIC_TELEMETRY_AND_LEDS.md      # Telemetry channels, RPM calculations & LED schemas
│   ├── LMU_API_AND_VEHICLE_MAPPING.md     # LMU embedded REST endpoints & vehicle tokens
│   └── ROADMAP_AND_ARCHITECTURE.md        # Technical roadmap (Profile Switching & CAN-FD LEDs)
│
├── src/simagic_daemon/                    # Core daemon package
│   ├── __init__.py                        # Package exports & version
│   ├── __main__.py                        # python -m simagic_daemon entrypoint
│   ├── daemon.py                          # Main background polling service & CLI
│   ├── simagic_client.py                  # High-level SimPro v3 REST API client
│   ├── vehicle_mapping.py                 # LMU vehicle resolver & preset UUID matrix
│   └── lmu_reader.py                      # LMU REST API & Shared Memory telemetry reader
│
├── tools/                                 # Standalone CLI diagnostic utilities
│   ├── test_simagic_connection.py         # Hardware & SimPro REST API diagnostic
│   └── test_lmu_connection.py             # LMU connection & vehicle resolver tester
│
├── .gitignore
├── LICENSE                                # MIT License
├── pyproject.toml                         # Packaging metadata & entrypoint definitions
└── README.md
```

---

## 🚀 Getting Started

### Prerequisites
* Windows 10 or 11
* Python 3.10+
* **SimPro Manager v3** running in the background
* **Le Mans Ultimate (LMU)**

### Installation

Clone the repository and install the daemon in editable mode:

```bash
git clone https://github.com/hockeylagu/simagic-wheel-daemon.git
cd simagic-wheel-daemon
pip install -e .
```

---

## 🎮 Usage

### 1. Run the Daemon
Start the background daemon to begin monitoring LMU sessions:

```bash
python -m simagic_daemon
```
*Or, if installed via `pip`:*
```bash
simagic-daemon
```

### CLI Options

| Flag | Description | Default |
| :--- | :--- | :--- |
| `--poll-interval`, `-i` | Polling rate in seconds | `1.0` |
| `--dry-run` | Log profile switches without calling SimPro API | `False` |
| `--revert-on-exit` | Revert GT NEO to default preset when LMU exits | `False` |
| `--once` | Run a single poll cycle and exit | `False` |
| `--verbose`, `-v` | Enable verbose / debug logging | `False` |

#### Dry Run Example:
```bash
python -m simagic_daemon --dry-run
```

#### Revert to Default Profile on Game Exit:
```bash
python -m simagic_daemon --revert-on-exit
```

---

## 🔧 Diagnostic Tools

### Test Simagic Hardware & SimPro REST API
Verifies connectivity to SimPro Manager (`127.0.0.1:4010`), lists connected hardware (Base, Wheel, Pedals) and their firmware versions, and catalogs all saved presets:

```bash
python tools/test_simagic_connection.py
```

### Test Le Mans Ultimate Telemetry & Vehicle Mapping
Verifies connectivity to LMU's embedded REST server (`http://localhost:6397`) and Shared Memory, testing vehicle resolution against the simulated grid:

```bash
python tools/test_lmu_connection.py
```

---

## 🚘 Supported Vehicle Profiles

The daemon maps LMU car models to your custom SimPro GT NEO profiles:

| LMU Vehicle Class / Model | GT NEO Profile | SimPro Preset UUID |
| :--- | :--- | :--- |
| **Ferrari 296 GT3** | `GT3 296` | `<WHEEL_PRESET_UUID_296>` |
| **McLaren 720S GT3 Evo** | `GT3 720S` | `<WHEEL_PRESET_UUID_720S>` |
| **Porsche 911 GT3 R** | `GT3 911` | `<WHEEL_PRESET_UUID_911>` |
| **BMW M4 GT3** | `GT3 M4` | `<WHEEL_PRESET_UUID_M4>` |
| **Ford Mustang GT3** | `GT3 Mustang` | `<WHEEL_PRESET_UUID_MUSTANG>` |
| **Lexus RC F GT3** | `GT3 RCF` | `<WHEEL_PRESET_UUID_RCF>` |
| **Corvette Z06 GT3.R** | `GT3 Vette` | `<WHEEL_PRESET_UUID_VETTE>` |
| **Aston Martin Vantage GTE** | `GTE AMR` | `<WHEEL_PRESET_UUID_AMR>` |
| **Cadillac V-Series.R** | `HYP Cadillac` | `<WHEEL_PRESET_UUID_CADILLAC>` |
| **Peugeot 9X8** | `HYP Peugeot` | `<WHEEL_PRESET_UUID_PEUGEOT>` |
| **Aston Martin Valkyrie LMH** | `HYP Valkyrie` | `<WHEEL_PRESET_UUID_VALKYRIE>` |
| **Oreca 07 LMP2** | `LM P2` | `<WHEEL_PRESET_UUID_LMP2>` |
| **Ginetta G61-LT-P325 LMP3** | `LMP3 Ginetta` | `<WHEEL_PRESET_UUID_GINETTA>` |
| **Fallback / Other** | `My GT Neo Default` | `<WHEEL_PRESET_UUID_DEFAULT>` |

*Wheelbase profile automatically targets **`My LeMans Ultimate`** (`<BASE_PRESET_UUID>`).*

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
