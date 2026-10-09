# 🏎️ simagic-wheel-daemon

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](https://www.microsoft.com/windows)
[![CAN-FD Native](https://img.shields.io/badge/CAN--FD-Quick%20Release-brightgreen.svg)]()

**simagic-wheel-daemon** is a lightweight, standalone automation daemon for **Simagic** direct-drive ecosystems (Alpha EVO Sport wheelbase, GT NEO steering wheel, P700 pedals). It provides automatic, per-vehicle profile switching and accurate RPM rev light calibration in **Le Mans Ultimate (LMU)** running **100% over CAN-FD** through the Simagic Quick Release—without requiring a Maglink USB cable.

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
│   Profile activated instantly. Rev lights match in-game tachometer.    │
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

### 🖥️ Windows Tray Application (Recommended)

Run the daemon as a native Windows tray app that lives quietly in the taskbar notification area (system tray next to the Windows clock):

* **Launch Silently (No Console Window)**: Double-click **`SimagicWheelDaemon.vbs`** or run:
  ```bash
  pythonw -m simagic_daemon.tray
  ```
  *(Or `simagic-tray` when installed via pip)*
* **Launch with Console**: Double-click **`SimagicWheelDaemon.bat`**

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
