"""Unit tests for can_network/bus_config.py — backend/channel resolution (the HAL seam)."""
import importlib

import can_network.bus_config as bus_config


def reload_with_env(monkeypatch, **env):
    for key in ("CAN_INTERFACE", "CAN_CHANNEL", "CAN_ATTACKER_CHANNEL", "CAN_SERIAL", "CAN_BITRATE"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    importlib.reload(bus_config)
    return bus_config


def test_defaults_to_socketcan_vcan0(monkeypatch):
    bc = reload_with_env(monkeypatch)
    assert bc.bus_kwargs() == {
        "interface": "socketcan",
        "channel": "vcan0",
        "receive_own_messages": True,
    }


def test_explicit_channel_overrides_default(monkeypatch):
    bc = reload_with_env(monkeypatch)
    assert bc.bus_kwargs("vcan1")["channel"] == "vcan1"


def test_socketcan_ignores_serial_and_bitrate(monkeypatch):
    bc = reload_with_env(monkeypatch, CAN_SERIAL="ABC123", CAN_BITRATE="500000")
    kwargs = bc.bus_kwargs()
    assert "serial" not in kwargs
    assert "bitrate" not in kwargs


def test_ics_neovi_picks_up_serial_and_bitrate_from_env(monkeypatch):
    bc = reload_with_env(
        monkeypatch,
        CAN_INTERFACE="ics_neovi",
        CAN_CHANNEL="HSCAN",
        CAN_SERIAL="ABC123",
        CAN_BITRATE="500000",
    )
    kwargs = bc.bus_kwargs()
    assert kwargs == {
        "interface": "ics_neovi",
        "channel": "HSCAN",
        "receive_own_messages": True,
        "serial": "ABC123",
        "bitrate": 500000,
    }


def test_explicit_serial_wins_over_env_serial(monkeypatch):
    bc = reload_with_env(monkeypatch, CAN_INTERFACE="ics_neovi", CAN_SERIAL="ENV_SERIAL")
    kwargs = bc.bus_kwargs("HSCAN", serial="EXPLICIT_SERIAL")
    assert kwargs["serial"] == "EXPLICIT_SERIAL"


def test_two_devices_get_independent_kwargs(monkeypatch):
    """The two-Intrepid-device scenario: each script's serial/channel stay independent."""
    bc = reload_with_env(monkeypatch, CAN_INTERFACE="ics_neovi")
    client_kwargs = bc.bus_kwargs("HSCAN", serial="CLIENT_SN")
    controls_kwargs = bc.bus_kwargs("HSCAN2", serial="CONTROLS_SN")
    assert client_kwargs["serial"] == "CLIENT_SN"
    assert controls_kwargs["serial"] == "CONTROLS_SN"
    assert client_kwargs["channel"] == "HSCAN"
    assert controls_kwargs["channel"] == "HSCAN2"
