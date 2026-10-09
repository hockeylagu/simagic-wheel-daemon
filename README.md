# 🏎️ simagic-wheel-daemon

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](https://www.microsoft.com/windows)
[![CAN-FD Native](https://img.shields.io/badge/CAN--FD-Quick%20Release-brightgreen.svg)]()

**simagic-wheel-daemon** is a lightweight, standalone automation daemon for **Simagic** direct-drive ecosystems (Alpha EVO Sport wheelbase, GT NEO steering wheel, P700 pedals). It provides automatic, per-vehicle profile switching in **Le Mans Ultimate (LMU)**, so each car gets the rev-light thresholds, buttons and FFB stored in its own SimPro profile, running **100% over CAN-FD** through the Simagic Quick Release—without requiring a Maglink USB cable.

---

## 🌟 Key Features

* **⚡ Automatic Per-Vehicle Profile Switching:** Automatically detects when you load into any car in Le Mans Ultimate and switches the active profile on both your **Wheelbase** (FFB, rotation angle, damping) and **GT NEO Steering Wheel** (button mappings, clutch bite point, LED themes, rev lights).
* **🏎️ CAN-FD Quick Release Operation:** Communicates through the quick release pogo pins via native CAN-FD. No Maglink USB cable required; keep your cockpit wireless and clutter-free.
* **🛡️ 100% Safe (Zero Bricking Risk):** Interacts exclusively with SimPro Manager's official local REST API (`http://127.0.0.1:4010/simpro/api/v3/`). Never touches microcontroller flash or bootloaders; all adjustments update volatile RAM runtime parameters identically to official GUI clicks.
* **🔒 Anti-Cheat Compliant:** Reads LMU game states using LMU's embedded HTTP REST API (`http://localhost:6397`) and official rFactor 2 shared memory (`$rFactor2SMMP_Scoring$`). Zero DLL injection, zero memory hooks.
* **📦 Lightweight & Standalone:** Operates as a focused, self-contained background service that directly bridges LMU and SimPro Manager without unnecessary overhead.


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
│   Profile activated instantly: that car's rev lights, buttons & FFB.   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🗺️ Code Map & Documentation

For the complete file index, module responsibilities, and architecture flows, see **[`CODE_MAP.md`](CODE_MAP.md)**.
In-depth technical research, telemetry analyses, and protocol references are located in **[`docs/`](docs/)**.

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

### ⚙️ First-Time Setup (generate your private config)

The daemon needs two files that are specific to your hardware and your LMU install. They are
generated on your machine into the gitignored `local/` folder and are never committed or shared.

| File | Contains | Generated from |
| :--- | :--- | :--- |
| `local/user_presets.json` | Your device IDs and which SimPro profile to use for each car | SimPro Manager's local database |
| `local/lmu_vehicle_catalog.json` | Every installed LMU car/livery ID with its model and class | LMU's REST API (`/rest/sessions/getAllVehicles`) |

**1. Create your profiles in SimPro Manager.** Make one GT NEO profile per car (or class) you want, tag it
with **Le Mans Ultimate** in SimPro, and name it after the car, e.g. `GT3 296`, `HYP Cadillac`, `LM P2`,
`LMP3 Ginetta`. The setup tool recognises these names (and names containing the car, such as `Porsche 963`).
Also create one wheelbase profile tagged LMU, and a wheel profile with `Default` in its name as fallback.

**2. Generate `user_presets.json` from SimPro** (SimPro does not need to be running):
```bash
python tools/setup_user_presets.py --dry-run
python tools/setup_user_presets.py
```
It lists which profile was matched to each key and which keys fall back to another profile. Unset keys are
fine: for example, without a `HYP 499P` profile the Ferrari 499P uses `HYP Cadillac`. Run it again whenever
you add profiles; existing values are kept unless you pass `--overwrite`.

**3. Vehicle catalog: automatic.** LMU team liveries have IDs such as `12_24_JOTAA5525C5E` that do not name
the car; the catalog lets the daemon identify every one of them exactly. The daemon builds and refreshes it by
itself from LMU's REST API: once each time LMU starts, and again whenever a car it does not know is loaded
(new DLC, game updates). If the current car is re-identified, its profile is switched right away.
To build it by hand and see what was added (LMU running):
```bash
python tools/generate_vehicle_catalog.py
```

**4. Check the result:**
```bash
python tools/validate_vehicle_mapping.py
```
It resolves every vehicle ID in your catalog and reports any car that would get the wrong profile.

---

### 🖥️ Windows Tray Application (Recommended)

Run the daemon as a native Windows tray app that lives quietly in the taskbar notification area (system tray next to the Windows clock):

* **Launch**: Double-click **`SimagicWheelDaemon.bat`**, or the **Simagic Wheel Daemon** Start Menu shortcut
  (create it once with `python tools/create_windows_shortcuts.py`). Both start the tray app silently with
  `pythonw.exe SimagicWheelDaemon.pyw`: no console window and no VBScript, which recent Windows 11 builds
  no longer ship enabled.
* **From a terminal**:
  ```bash
  pythonw SimagicWheelDaemon.pyw
  ```

#### System Tray Controls (Right-Click Menu):
* **Live Status Display**:
  * 🎮 **Game**: Real-time Le Mans Ultimate process status (*Running / Not Running*).
  * 🏎️ **Car**: Currently detected car model in session.
  * ⚙️ **Profile**: Currently active GT NEO profile.
  * 🔌 **SimPro**: Real-time SimPro Manager v3 connection health.
* **Interactive Actions**:
  * 🔔 **Test Notification**: Verifies native Windows Toast notifications.
  * 🚀 **Launch SimPro Manager**: Launches `simpro3.exe` if not running.
  * ⚙️ **Revert Profile on Exit**: Toggle automatic fallback to default profile when exiting LMU.
  * 🛑 **Stop Daemon**: 1-click clean shutdown of the daemon service.

#### Desktop & Start Menu Shortcuts:
Generate convenient Windows shortcuts with the authentic GT NEO icon:
```bash
python tools/create_windows_shortcuts.py
```
*(Optionally pass `--startup` to automatically start with Windows).*


---

### 💻 CLI Service Mode
You can also run the daemon directly from your terminal:

```bash
python -m simagic_daemon
```
*Or via console script:*
```bash
simagic-daemon
```

### CLI Options

| Flag | Description | Default |
| :--- | :--- | :--- |
| `--poll-interval`, `-i` | Polling rate in seconds | `1.0` |
| `--dry-run` | Log profile switches without calling SimPro API | `False` |
| `--revert-on-exit` | Revert GT NEO to default preset when LMU exits | `False` |
| `--no-notify` | Disable Windows desktop toast notifications | `False` |
| `--auto-launch-simpro` | Automatically start SimPro if not running | `False` |
| `--debug`, `-d` | Enable verbose debug logging to console and rotating file | `False` |
| `--verbose`, `-v` | Enable verbose logging | `False` |
| `--log-file` | Custom path for the rotating log file | `logs/daemon.log` |
| `--no-catalog-sync` | Do not refresh the vehicle catalog from LMU's REST API automatically | `False` |
| `--verify-interval` | Seconds between checks that the active profile still matches the car (re-applied if changed externally); `0` disables | `15` |
| `--capture [DIR]` | Record raw LMU data (REST + shared memory) instead of running the daemon; replay with `python tools/replay_capture.py DIR` | `local/captures/<timestamp>` |

Only one daemon (console or tray) can run at a time; a second instance exits immediately.
`SimagicWheelDaemon.pyw` (used by the `.bat` and the shortcuts) always runs the code in this folder's `src/`, regardless of any other pip-installed copy.

---

## 🔧 Diagnostic & Inspection Tools

### 1. View & Follow Debug Logs
Inspect real-time daemon logs or open them in Notepad:

```bash
# View recent 35 log lines
python tools/view_logs.py

# Live follow/tail logs in console
python tools/view_logs.py --follow

# Open log file directly in Windows Notepad
python tools/view_logs.py --open
```

### 2. Test Simagic Hardware & SimPro REST API
Verifies connectivity to SimPro Manager (`127.0.0.1:4010`), lists connected hardware (Base, Wheel, Pedals) and their firmware versions, and catalogs all saved presets:

```bash
python tools/test_simagic_connection.py
```

### 3. Test Le Mans Ultimate Telemetry & Vehicle Mapping
Verifies connectivity to LMU's embedded REST server (`http://localhost:6397`) and Shared Memory, testing vehicle resolution against the simulated grid:

```bash
python tools/test_lmu_connection.py
```

### 4. Create Desktop & Start Menu Shortcuts
Creates customized `.lnk` Windows shortcuts configured with the GT NEO icon:

```bash
# Standard Desktop and Start Menu shortcuts
python tools/create_windows_shortcuts.py

# Add to Windows Startup folder as well
python tools/create_windows_shortcuts.py --startup
```

### 5. Generate Application Icons
Processes source steering wheel photos into centered 512x512 PNG and multi-resolution Windows ICO (`16x16` through `256x256`):

```bash
python tools/update_icon.py
```


---


## 📄 License

This project is licensed under the [MIT License](LICENSE).
