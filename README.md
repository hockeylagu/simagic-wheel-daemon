# 🏎️ simagic-wheel-daemon

**simagic-wheel-daemon** is a lightweight, standalone automation daemon for **Simagic** direct-drive ecosystems. It enables automatic, per-vehicle profile switching and accurate RPM rev light calibration in **Le Mans Ultimate (LMU)** running **100% over CAN-FD** through the Simagic Quick Release—without requiring a Maglink USB cable or third-party tools like SimHub.


---

## 🌟 Key Features

* **⚡ Automatic Per-Vehicle Profile Switching:** Automatically detects when you load into a car in Le Mans Ultimate and switches the active profile on both your **Wheelbase** (FFB, rotation angle, damping) and **GT NEO Steering Wheel** (button bindings, clutch bite point, LED themes).
* **🏎️ Accurate In-Game RPM Matching over CAN-FD:** Overcomes SimPro's generic linear RPM percentage calculation by calibrating true per-car shift points, rev light patterns, and Pit Limiter / TC visual alerts directly over the wheelbase's CAN-FD bus.
* **🔌 No Maglink USB Cable Required:** Communicates through the quick release pogo pins via native CAN-FD. Keep your cockpit wireless and clutter-free.
* **🛡️ 100% Safe (Zero Bricking Risk):** Interacts exclusively with SimPro Manager's official internal REST API (`http://127.0.0.1:4010/simpro/api/v3/`). Never touches microcontroller flash or bootloaders; all adjustments update volatile RAM runtime parameters identically to official GUI clicks.
* **🔒 Anti-Cheat Compliant:** Reads LMU game states using LMU's embedded HTTP REST API (`http://localhost:6397`) and official rFactor 2 shared memory (`$rFactor2SMMP_Scoring$`). Zero DLL injection, zero memory hooks.

---

## 🏗️ Architecture

```
+------------------------------------------------------------------------------------+
|                               Le Mans Ultimate (LMU)                               |
|  - Embedded REST API (http://localhost:6397/navigation/state)                       |
|  - rFactor 2 Shared Memory Map ($rFactor2SMMP_Scoring$)                            |
+------------------------------------------------------------------------------------+
                                         │
                                         ▼ (HTTP GET / Read-only Win32 mmap)
+------------------------------------------------------------------------------------+
|                              WheelDaemon (Python Engine)                           |
|  1. Detects vehicle identity (e.g. 296_GT3.veh, ORECA_07.veh, CADILLAC_V-SERIES.R)  |
|  2. Resolves vehicle to target SimPro preset UUIDs via lmu_vehicle_mapping.py      |
|  3. Sends HTTP POST to SimPro Manager local REST server                            |
+------------------------------------------------------------------------------------+
                                         │
                                         ▼ (HTTP POST to http://127.0.0.1:4010/simpro/api/v3/)
+------------------------------------------------------------------------------------+
|                                SimPro Manager v3                                   |
|  - preset_select_dev_config: Selects wheelbase & wheel profiles                     |
|  - preset_set_dev_config: Applies calibrated RPM threshold curves                  |
|  - Packages frames via SCommUsbHid::writeOutReportCanfdSync()                       |
+------------------------------------------------------------------------------------+
                                         │
                                         ▼ (USB HID -> CAN-FD Quick Release Pogo Pins)
+------------------------------------------------------------------------------------+
|                       Simagic Base  ──►  GT NEO Steering Wheel                     |
|  Profile activated. Rev lights match in-game tachometer pixel-for-pixel.           |
+------------------------------------------------------------------------------------+
```

---

## 📁 Repository Structure

| File | Description |
| :--- | :--- |
| **[`lmu_vehicle_mapping.py`](lmu_vehicle_mapping.py)** | Vehicle token resolver linking LMU vehicle files to SimPro preset UUIDs. |
| **[`lmu_reader.py`](lmu_reader.py)** | Read-only shared memory reader for rFactor 2 / LMU telemetry. |
| **[`simagic_client.py`](simagic_client.py)** | Python client for querying SimPro presets and executing safe profile switches. |
| **[`SIMAGIC_RESEARCH_FINDINGS.md`](SIMAGIC_RESEARCH_FINDINGS.md)** | Technical deep-dive on SimPro's internal daemon, IPC, REST API, and CAN-FD layer. |
| **[`SIMAGIC_TELEMETRY_AND_LEDS.md`](SIMAGIC_TELEMETRY_AND_LEDS.md)** | Specification of SimPro's telemetry channels, RPM calculations, and LED schemas. |
| **[`LMU_API_AND_VEHICLE_MAPPING.md`](LMU_API_AND_VEHICLE_MAPPING.md)** | LMU embedded API discovery and token resolution matrix. |
| **[`ROADMAP_AND_ARCHITECTURE.md`](ROADMAP_AND_ARCHITECTURE.md)** | Engineering roadmap for Goal 1 (Profile Switching) and Goal 2 (CAN-FD LEDs). |
| **[`LICENSE`](LICENSE)** | MIT License. |

---

## 🚀 Quick Start

### Prerequisites
* Windows 10 / 11
* Python 3.10+
* SimPro Manager v3 running in the background
* Le Mans Ultimate (LMU)

### 1. Test Device Connectivity
To verify that SimPro's local REST API is accessible and inspect your saved profiles:
```bash
python simagic_client.py
```

### 2. Test Vehicle Resolution
To verify token resolution from LMU vehicle names to SimPro presets:
```bash
python lmu_vehicle_mapping.py
```

### 3. Check LMU Shared Memory
To verify read-only connection to the simulation telemetry:
```bash
python lmu_reader.py
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
