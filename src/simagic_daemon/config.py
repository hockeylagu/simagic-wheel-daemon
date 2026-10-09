"""
User Configuration Loader
Locates and loads the private `user_presets.json` (hardware UUIDs & preset UUIDs).

The same search order is used for other private files in local/ (e.g. lmu_vehicle_catalog.json).
Search order (first existing file wins):
1. `SIMAGIC_DAEMON_CONFIG` environment variable (explicit path)
2. `local/user_presets.json` in the current working directory
3. `local/user_presets.json` in the repository root (editable installs)
4. `%APPDATA%\\SimagicWheelDaemon\\user_presets.json` (regular pip installs)
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger("simagic_daemon.config")

CONFIG_FILENAME = "user_presets.json"
CONFIG_ENV_VAR = "SIMAGIC_DAEMON_CONFIG"

_cached_config: Optional[Dict[str, Any]] = None
_cached_path: Optional[str] = None


def candidate_local_paths(filename: str, env_var: Optional[str] = None) -> List[str]:
    """Returns every location searched for a private local file, in priority order."""
    paths = []
    env_path = os.environ.get(env_var) if env_var else None
    if env_path:
        paths.append(os.path.abspath(os.path.expandvars(env_path)))
    paths.append(os.path.abspath(os.path.join(os.getcwd(), "local", filename)))
    paths.append(os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "local", filename)
    ))
    appdata = os.environ.get("APPDATA")
    if appdata:
        paths.append(os.path.join(appdata, "SimagicWheelDaemon", filename))

    # De-duplicate while preserving order
    seen = set()
    return [p for p in paths if not (os.path.normcase(p) in seen or seen.add(os.path.normcase(p)))]


def find_local_file(filename: str, env_var: Optional[str] = None) -> Optional[str]:
    """Returns the first existing path for a private local file, or None."""
    for path in candidate_local_paths(filename, env_var):
        if os.path.isfile(path):
            return path
    return None


def candidate_config_paths() -> List[str]:
    """Returns every location searched for the user configuration, in priority order."""
    return candidate_local_paths(CONFIG_FILENAME, CONFIG_ENV_VAR)


def find_config_path() -> Optional[str]:
    """Returns the first existing configuration file path, or None."""
    return find_local_file(CONFIG_FILENAME, CONFIG_ENV_VAR)


def load_config() -> Dict[str, Any]:
    """Loads (and caches) the user configuration. Returns {} if none is found or it is invalid."""
    global _cached_config, _cached_path
    if _cached_config is not None:
        return _cached_config

    path = find_config_path()
    config: Dict[str, Any] = {}
    if path:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                config = data
                logger.debug(f"[Config] Loaded user configuration from {path}")
            else:
                logger.warning(f"[Config] Ignoring {path}: top-level JSON value is not an object")
        except Exception as e:
            logger.warning(f"[Config] Failed to load {path}: {e}")
    else:
        logger.warning(
            "[Config] No user_presets.json found. Searched: " + "; ".join(candidate_config_paths())
        )

    _cached_config = config
    _cached_path = path
    return config


def get_config_value(key: str, default: str = "") -> str:
    """Returns a configuration value as a string (SimPro requires string UUIDs)."""
    value = load_config().get(key)
    return str(value) if value not in (None, "") else default
