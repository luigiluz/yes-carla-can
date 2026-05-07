"""Unit tests for can_network/network.py — CARLA↔CAN value encoding and decoding."""
import pytest
from unittest.mock import MagicMock, patch

from can_network.network import CAN_Network
from constants import FULL_DBC


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def dbc_path(tmp_path_factory):
    """Temporary DBC file with all required messages plus GENERAL_LIGHTS, scoped to the module."""
    p = tmp_path_factory.mktemp("dbc") / "carla.dbc"
    p.write_text(FULL_DBC)
    return p


@pytest.fixture
def net_and_bus(dbc_path):
    """Return a (CAN_Network, mock_bus) pair with the SocketCAN bus mocked out."""
    mock_bus = MagicMock()
    with patch("can.ThreadSafeBus", return_value=mock_bus):
        net = CAN_Network(dbc_path=str(dbc_path), channel="vcan0")
    return net, mock_bus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decode_last_sent(net, mock_bus):
    """Decode the can.Message that was most recently passed to mock_bus.send."""
    sent_msg = mock_bus.send.call_args[0][0]
    return net.db.decode_message(sent_msg.arbitration_id, sent_msg.data)


def _recv_one_frame(net, mock_bus, frame):
    """Drive recv_msg with a single real CAN frame followed by None (end-of-queue)."""
    mock_bus.recv.side_effect = [frame, None]
    return net.recv_msg()


# ---------------------------------------------------------------------------
# Throttle encoding
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("throttle, expected_byte", [
    (0.0, 0),
    (1.0, 255),
    (0.5, 127),  # int(0.5 * 255) = int(127.5) = 127
])
def test_throttle_encoding(net_and_bus, throttle, expected_byte):
    """throttle ∈ [0, 1] is linearly mapped to [0, 255]."""
    net, mock_bus = net_and_bus
    controls = MagicMock()
    controls.throttle = throttle
    net.send_throttle_msg(controls)
    assert _decode_last_sent(net, mock_bus)["THROTTLE_signal"] == expected_byte


# ---------------------------------------------------------------------------
# Steer encoding  (−1 → 0,  +1 → 255 — boundary values are exact)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("steer, expected_byte", [
    (-1.0, 0),    # full left lock
    (+1.0, 255),  # full right lock
])
def test_steer_encoding_boundaries(net_and_bus, steer, expected_byte):
    """steer ∈ [−1, +1] is linearly mapped to [0, 255]; boundary values are exact."""
    net, mock_bus = net_and_bus
    controls = MagicMock()
    controls.steer = steer
    net.send_steer_msg(controls)
    assert _decode_last_sent(net, mock_bus)["STEER_signal"] == expected_byte


# ---------------------------------------------------------------------------
# Brake encoding
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("brake, expected_byte", [
    (0.0, 0),
    (1.0, 255),
])
def test_brake_encoding(net_and_bus, brake, expected_byte):
    """brake ∈ [0, 1] is linearly mapped to [0, 255]."""
    net, mock_bus = net_and_bus
    controls = MagicMock()
    controls.brake = brake
    net.send_brake_msg(controls)
    assert _decode_last_sent(net, mock_bus)["BRAKE_signal"] == expected_byte


# ---------------------------------------------------------------------------
# Lights mask  (CARLA VehicleLightState can exceed one byte; must be masked)
# ---------------------------------------------------------------------------


def test_lights_value_exceeding_byte_is_masked(net_and_bus):
    """VehicleLightState values > 0xFF are truncated to one byte before encoding."""
    net, mock_bus = net_and_bus
    net.send_current_lights_msg(0x1FF)
    assert _decode_last_sent(net, mock_bus)["GENERAL_LIGHTS_signal"] == 0xFF


# ---------------------------------------------------------------------------
# Receive-path decoding
# ---------------------------------------------------------------------------


def test_recv_throttle_full_decodes_to_one(net_and_bus):
    """Byte value 255 on the THROTTLE frame decodes to throttle = 1.0."""
    net, mock_bus = net_and_bus
    frame = net._build_msg("THROTTLE", 255)
    result = _recv_one_frame(net, mock_bus, frame)
    assert result.throttle == pytest.approx(1.0)


def test_recv_throttle_zero_decodes_to_zero(net_and_bus):
    """Byte value 0 on the THROTTLE frame decodes to throttle = 0.0."""
    net, mock_bus = net_and_bus
    frame = net._build_msg("THROTTLE", 0)
    result = _recv_one_frame(net, mock_bus, frame)
    assert result.throttle == pytest.approx(0.0)


def test_recv_steer_zero_byte_decodes_to_full_left(net_and_bus):
    """Byte value 0 on the STEER frame decodes to steer = −1.0 (full left)."""
    net, mock_bus = net_and_bus
    frame = net._build_msg("STEER", 0)
    result = _recv_one_frame(net, mock_bus, frame)
    assert result.steer == pytest.approx(-1.0)


def test_recv_steer_max_byte_decodes_to_full_right(net_and_bus):
    """Byte value 255 on the STEER frame decodes to steer = +1.0 (full right)."""
    net, mock_bus = net_and_bus
    frame = net._build_msg("STEER", 255)
    result = _recv_one_frame(net, mock_bus, frame)
    assert result.steer == pytest.approx(1.0)
