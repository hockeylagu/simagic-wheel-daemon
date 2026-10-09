# 🗺️ Code Map: simagic-wheel-daemon

The complete architectural index, data flow specifications, and module directory are located in **[`docs/CODE_MAP.md`](docs/CODE_MAP.md)**.

### Quick Reference:

| Component | Path | Description |
| :--- | :--- | :--- |
| **Agent Guidelines** | **[`AGENT.md`](AGENT.md)** | Rules, safety constraints & hardware invariants for AI agents. |
| **Code Map** | **[`docs/CODE_MAP.md`](docs/CODE_MAP.md)** | Full architectural map, data flows, and module responsibilities. |
| **Main Daemon** | **[`src/simagic_daemon/daemon.py`](src/simagic_daemon/daemon.py)** | Background service connecting LMU to SimPro Manager. |
| **SimPro REST Client** | **[`src/simagic_daemon/simagic_client.py`](src/simagic_daemon/simagic_client.py)** | Safe HTTP client interfacing with Port 4010. |
| **Vehicle Resolver** | **[`src/simagic_daemon/vehicle_mapping.py`](src/simagic_daemon/vehicle_mapping.py)** | Resolves LMU car models to GT NEO preset UUIDs. |
| **LMU Telemetry Reader**| **[`src/simagic_daemon/lmu_reader.py`](src/simagic_daemon/lmu_reader.py)** | LMU embedded REST API (:6397) & shared memory reader. |
| **Diagnostics** | **[`tools/`](tools/)** | Hardware and game connectivity test scripts. |

For deep technical research and protocols, see the **[`docs/`](docs/)** directory.
