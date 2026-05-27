"""Pytest session configuration — installs a carla stub so tests run without a live CARLA server."""
import sys
from unittest.mock import MagicMock

# carla requires a live CARLA server; replace it with a stub for testing.
if "carla" not in sys.modules:
    _carla_stub = MagicMock(name="carla_stub")
    # VehicleLightState: callable returns the integer value; attributes are the flag constants.
    _carla_stub.VehicleLightState = MagicMock(side_effect=int)
    _carla_stub.VehicleLightState.NONE         = 0
    _carla_stub.VehicleLightState.Position     = 0x001
    _carla_stub.VehicleLightState.LowBeam      = 0x002
    _carla_stub.VehicleLightState.HighBeam     = 0x004
    _carla_stub.VehicleLightState.Brake        = 0x008
    _carla_stub.VehicleLightState.RightBlinker = 0x010
    _carla_stub.VehicleLightState.LeftBlinker  = 0x020
    _carla_stub.VehicleLightState.Reverse      = 0x040
    _carla_stub.VehicleLightState.Fog          = 0x080
    _carla_stub.VehicleLightState.Interior     = 0x100
    _carla_stub.VehicleLightState.Special1     = 0x200
    _carla_stub.VehicleLightState.Special2     = 0x400
    _carla_stub.VehicleLightState.All          = 0x7FF
    sys.modules["carla"] = _carla_stub
