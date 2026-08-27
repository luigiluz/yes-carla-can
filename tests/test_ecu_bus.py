"""Unit tests for the ECU bus split (can_network.dbc.BUS_ASSIGNMENT + CAN_Network(ecu_bus=...))."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from can_network.network import CAN_Network
from constants import SENSOR_DBC


@pytest.fixture(scope="module")
def sensor_dbc_path(tmp_path_factory):
    p = tmp_path_factory.mktemp("ecu_bus_dbc") / "sensor.dbc"
    p.write_text(SENSOR_DBC)
    return p


def _make_ecu(dbc_path, ecu_bus):
    with patch("can.ThreadSafeBus", return_value=MagicMock()):
        return CAN_Network(dbc_path=str(dbc_path), channel="vcan0", ecu_bus=ecu_bus)


def test_powertrain_cycle_times_excludes_comfort_messages(sensor_dbc_path):
    powertrain_ecu = _make_ecu(sensor_dbc_path, "POWERTRAIN")
    assert set(powertrain_ecu.cycle_times) == {
        "THROTTLE", "BRAKE", "STEER", "REVERSE", "HAND_BRAKE",
        "MANUAL_TRANSMISSION", "GEAR",
    }


def test_comfort_cycle_times_excludes_powertrain_messages(sensor_dbc_path):
    comfort_ecu = _make_ecu(sensor_dbc_path, "COMFORT")
    assert "GNSS" in comfort_ecu.cycle_times
    assert not (set(comfort_ecu.cycle_times) & {"THROTTLE", "BRAKE", "STEER"})


def test_sending_comfort_message_on_powertrain_ecu_raises(sensor_dbc_path):
    powertrain_ecu = _make_ecu(sensor_dbc_path, "POWERTRAIN")
    with pytest.raises(ValueError):
        powertrain_ecu.send_gnss_msg(1.0, 2.0)


def test_sending_powertrain_message_on_comfort_ecu_raises(sensor_dbc_path):
    comfort_ecu = _make_ecu(sensor_dbc_path, "COMFORT")
    with pytest.raises(ValueError):
        comfort_ecu.send_throttle_msg(SimpleNamespace(throttle=0.5))


def test_unscoped_network_keeps_todays_unfiltered_behavior(sensor_dbc_path):
    net = _make_ecu(sensor_dbc_path, None)
    assert "GNSS" in net.cycle_times
    assert "THROTTLE" in net.cycle_times
    net.send_throttle_msg(SimpleNamespace(throttle=0.5))  # does not raise
    net.send_gnss_msg(1.0, 2.0)  # does not raise
