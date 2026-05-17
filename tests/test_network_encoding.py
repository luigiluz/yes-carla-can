"""Unit tests for can_network/network.py — CARLA↔CAN value encoding and decoding."""
import pytest
from unittest.mock import MagicMock, patch

from can_network.network import CAN_Network
from constants import FULL_DBC, SENSOR_DBC


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def dbc_path(tmp_path_factory):
    """Temporary DBC file with all required messages plus GENERAL_LIGHTS, scoped to the module."""
    p = tmp_path_factory.mktemp("dbc") / "carla.dbc"
    p.write_text(FULL_DBC)
    return p


@pytest.fixture(scope="module")
def sensor_dbc_path(tmp_path_factory):
    """Temporary DBC file that also includes all 6 sensor messages."""
    p = tmp_path_factory.mktemp("sensor_dbc") / "sensor.dbc"
    p.write_text(SENSOR_DBC)
    return p


@pytest.fixture
def sensor_net_and_bus(sensor_dbc_path):
    """Return a (CAN_Network, mock_bus) pair backed by the sensor DBC."""
    mock_bus = MagicMock()
    with patch("can.ThreadSafeBus", return_value=mock_bus):
        net = CAN_Network(dbc_path=str(sensor_dbc_path), channel="vcan0")
    return net, mock_bus


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


# ---------------------------------------------------------------------------
# Sensor encoding — GNSS
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("lat, lon", [
    (48.8566, 2.3522),    # Paris
    (-33.8688, 151.2093), # Sydney (negative lat, large lon)
    (0.0, 0.0),           # null island
    (90.0, 180.0),        # extremes
])
def test_gnss_encoding_round_trip(sensor_net_and_bus, lat, lon):
    """GNSS lat/lon survive a full encode→decode cycle within one scale unit (1e-6 deg)."""
    net, mock_bus = sensor_net_and_bus
    net.send_gnss_msg(lat, lon)
    decoded = _decode_last_sent(net, mock_bus)
    assert decoded["GNSS_LAT_signal"] == pytest.approx(lat, abs=1e-6)
    assert decoded["GNSS_LON_signal"] == pytest.approx(lon, abs=1e-6)


# ---------------------------------------------------------------------------
# Sensor encoding — Collision
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("intensity, expected", [
    (0.0, 0.0),
    (42.5, 42.5),
    (6553.5, 6553.5),  # max representable value
])
def test_collision_encoding_round_trip(sensor_net_and_bus, intensity, expected):
    """Collision intensity survives encode→decode within the 0.1 scale resolution."""
    net, mock_bus = sensor_net_and_bus
    net.send_collision_msg(intensity)
    decoded = _decode_last_sent(net, mock_bus)
    assert decoded["COLLISION_INTENSITY_signal"] == pytest.approx(expected, abs=0.1)


def test_collision_intensity_clamped_at_uint16_max(sensor_net_and_bus):
    """Intensities beyond the representable range are clamped to 6553.5."""
    net, mock_bus = sensor_net_and_bus
    net.send_collision_msg(99999.0)
    decoded = _decode_last_sent(net, mock_bus)
    assert decoded["COLLISION_INTENSITY_signal"] == pytest.approx(6553.5, abs=0.1)


# ---------------------------------------------------------------------------
# Sensor encoding — Lane invasion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bitmask", [0b0000_0001, 0b0000_0110, 0b0111_1111_1111])
def test_lane_invasion_bitmask_round_trip(sensor_net_and_bus, bitmask):
    """Lane-invasion type bitmask survives encode→decode unchanged."""
    net, mock_bus = sensor_net_and_bus
    net.send_lane_invasion_msg(bitmask)
    decoded = _decode_last_sent(net, mock_bus)
    assert int(decoded["LANE_INVASION_TYPE_signal"]) == bitmask


# ---------------------------------------------------------------------------
# Sensor encoding — IMU
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("x, y, z", [
    (9.81, 0.0, -9.81),
    (0.0, 0.0, 0.0),
    (99.9, -99.9, 50.0),
])
def test_imu_accel_encoding_round_trip(sensor_net_and_bus, x, y, z):
    """IMU accelerometer values survive encode→decode within the 0.01 m/s² scale resolution."""
    net, mock_bus = sensor_net_and_bus
    net.send_imu_accel_msg(x, y, z)
    decoded = _decode_last_sent(net, mock_bus)
    assert decoded["IMU_ACCEL_X_signal"] == pytest.approx(x, abs=0.01)
    assert decoded["IMU_ACCEL_Y_signal"] == pytest.approx(y, abs=0.01)
    assert decoded["IMU_ACCEL_Z_signal"] == pytest.approx(z, abs=0.01)


@pytest.mark.parametrize("x, y, z", [
    (0.0, 0.0, 0.0),
    (45.0, -90.0, 180.0),
])
def test_imu_gyro_encoding_round_trip(sensor_net_and_bus, x, y, z):
    """IMU gyroscope values survive encode→decode within the 0.01 deg/s scale resolution."""
    net, mock_bus = sensor_net_and_bus
    net.send_imu_gyro_msg(x, y, z)
    decoded = _decode_last_sent(net, mock_bus)
    assert decoded["IMU_GYRO_X_signal"] == pytest.approx(x, abs=0.01)
    assert decoded["IMU_GYRO_Y_signal"] == pytest.approx(y, abs=0.01)
    assert decoded["IMU_GYRO_Z_signal"] == pytest.approx(z, abs=0.01)


@pytest.mark.parametrize("compass", [0.0, 90.0, 180.0, 270.0, 359.99])
def test_imu_compass_encoding_round_trip(sensor_net_and_bus, compass):
    """IMU compass angle survives encode→decode within the 0.01 deg scale resolution."""
    net, mock_bus = sensor_net_and_bus
    net.send_imu_compass_msg(compass)
    decoded = _decode_last_sent(net, mock_bus)
    assert decoded["IMU_COMPASS_signal"] == pytest.approx(compass, abs=0.01)
