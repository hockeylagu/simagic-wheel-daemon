"""
simagic-wheel-daemon
Standalone automation daemon for Simagic hardware and Le Mans Ultimate.
"""

__version__ = "0.1.0"
__author__ = "Samuel"

from .simagic_client import SimagicClient
from .vehicle_mapping import resolve_vehicle_to_preset
from .lmu_reader import LMUReader

__all__ = [
    "SimagicClient",
    "resolve_vehicle_to_preset",
    "LMUReader",
]
