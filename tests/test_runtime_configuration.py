"""Tests for configurable runtime interfaces used by Docker Compose."""

from unittest.mock import patch

from cyberattacks_module import parse_args as parse_attack_args
from gui.can_traffic_display import CANTrafficDisplay
from intrusion_detection_module import parse_args as parse_ids_args
from vehicle_controls_module import KeyboardSenderControl


def test_attack_cli_accepts_custom_vcan_interface():
    args = parse_attack_args(
        ["--feature", "hand_brake", "--period", "0.05", "--vcan", "vcan10"]
    )

    assert args.feature == "hand_brake"
    assert args.period == 0.05
    assert args.vcan == "vcan10"


def test_ids_cli_accepts_custom_vcan_interface():
    args = parse_ids_args(["--detector", "id_time", "--vcan", "vcan9"])

    assert args.detector == "id_time"
    assert args.vcan == "vcan9"


@patch("gui.can_traffic_display.threading.Thread")
@patch("gui.can_traffic_display.can.Bus")
def test_can_traffic_display_uses_configured_channel(mock_bus, mock_thread):
    display = CANTrafficDisplay(channel="vcan9")

    mock_bus.assert_called_once_with(interface="socketcan", channel="vcan9")
    mock_thread.assert_called_once()
    assert display.header == "CAN Traffic  (vcan9)"


def test_keyboard_sender_does_not_schedule_sensor_telemetry():
    can_net = type(
        "CanNetworkStub",
        (),
        {"cycle_times": {"THROTTLE": 0.1, "GNSS": 1.0, "IMU_ACCEL": 0.1}},
    )()

    sender = KeyboardSenderControl(can_net)

    assert set(sender._msg_timers) == {"THROTTLE"}
