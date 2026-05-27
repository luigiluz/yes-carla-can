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
# Lights encoding — individual flags map to individual 1-bit signals
# ---------------------------------------------------------------------------


def test_lights_only_position_sets_position_signal(net_and_bus):
    """Sending only Position (0x001) sets LIGHTS_Position_signal=1, all others 0."""
    net, mock_bus = net_and_bus
    net.send_current_lights_msg(0x001)
    decoded = _decode_last_sent(net, mock_bus)
    assert decoded["LIGHTS_Position_signal"] == 1
    assert decoded["LIGHTS_LowBeam_signal"] == 0
    assert decoded["LIGHTS_Brake_signal"] == 0


def test_lights_brake_and_reverse_set_correct_signals(net_and_bus):
    """Sending Brake|Reverse (0x008 | 0x040) sets only those two signals."""
    net, mock_bus = net_and_bus
    net.send_current_lights_msg(0x008 | 0x040)
    decoded = _decode_last_sent(net, mock_bus)
    assert decoded["LIGHTS_Brake_signal"] == 1
    assert decoded["LIGHTS_Reverse_signal"] == 1
    assert decoded["LIGHTS_Position_signal"] == 0
    assert decoded["LIGHTS_LowBeam_signal"] == 0


def test_lights_interior_special1_special2_are_not_dropped(net_and_bus):
    """Interior (0x100), Special1 (0x200), Special2 (0x400) are fully encoded — not silently dropped."""
    net, mock_bus = net_and_bus
    net.send_current_lights_msg(0x100 | 0x200 | 0x400)
    decoded = _decode_last_sent(net, mock_bus)
    assert decoded["LIGHTS_Interior_signal"] == 1
    assert decoded["LIGHTS_Special1_signal"] == 1
    assert decoded["LIGHTS_Special2_signal"] == 1
    assert decoded["LIGHTS_Position_signal"] == 0


def test_lights_all_sets_all_signals(net_and_bus):
    """VehicleLightState.All (0x7FF) sets all 11 light signals to 1."""
    net, mock_bus = net_and_bus
    net.send_current_lights_msg(0x7FF)
    decoded = _decode_last_sent(net, mock_bus)
    for sig in [
        "LIGHTS_Position_signal", "LIGHTS_LowBeam_signal", "LIGHTS_HighBeam_signal",
        "LIGHTS_Brake_signal", "LIGHTS_RightBlinker_signal", "LIGHTS_LeftBlinker_signal",
        "LIGHTS_Reverse_signal", "LIGHTS_Fog_signal", "LIGHTS_Interior_signal",
        "LIGHTS_Special1_signal", "LIGHTS_Special2_signal",
    ]:
        assert decoded[sig] == 1, f"Expected {sig} == 1"


def test_lights_none_clears_all_signals(net_and_bus):
    """VehicleLightState.NONE (0) sets all 11 light signals to 0."""
    net, mock_bus = net_and_bus
    net.send_current_lights_msg(0)
    decoded = _decode_last_sent(net, mock_bus)
    for sig in [
        "LIGHTS_Position_signal", "LIGHTS_LowBeam_signal", "LIGHTS_HighBeam_signal",
        "LIGHTS_Brake_signal", "LIGHTS_RightBlinker_signal", "LIGHTS_LeftBlinker_signal",
        "LIGHTS_Reverse_signal", "LIGHTS_Fog_signal", "LIGHTS_Interior_signal",
        "LIGHTS_Special1_signal", "LIGHTS_Special2_signal",
    ]:
        assert decoded[sig] == 0, f"Expected {sig} == 0"


def test_lights_roundtrip_all(net_and_bus):
    """Encode VehicleLightState.All then decode via recv_msg returns the same value (0x7FF)."""
    net, mock_bus = net_and_bus
    net.send_current_lights_msg(0x7FF)
    frame = mock_bus.send.call_args[0][0]
    mock_bus.recv.side_effect = [frame, None]
    net.recv_msg()
    assert net.current_lights == 0x7FF


def test_lights_roundtrip_partial(net_and_bus):
    """Encode LowBeam|Fog (0x082) then decode via recv_msg returns 0x082."""
    net, mock_bus = net_and_bus
    net.send_current_lights_msg(0x002 | 0x080)
    frame = mock_bus.send.call_args[0][0]
    mock_bus.recv.side_effect = [frame, None]
    net.recv_msg()
    assert net.current_lights == 0x002 | 0x080


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
