"""Pytest session configuration — installs a carla stub so tests run without a live CARLA server."""
import sys
from unittest.mock import MagicMock

# carla requires a live CARLA server; replace it with a stub for testing.
if "carla" not in sys.modules:
    _carla_stub = MagicMock(name="carla_stub")
    # CAN_Network uses carla.VehicleLightState.NONE as a class-body default.
    _carla_stub.VehicleLightState.NONE = 0
    sys.modules["carla"] = _carla_stub
