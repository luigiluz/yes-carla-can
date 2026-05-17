"""Unit tests for can_network/dbc.py — DBC loading and validation rules."""
import pytest
from can_network.dbc import load_and_validate, REQUIRED_MESSAGES, SUPPORTED_MESSAGES, SENSOR_MESSAGES
from constants import MINIMAL_DBC, SENSOR_DBC


@pytest.fixture
def valid_dbc(tmp_path):
    """Temporary DBC file with all required messages."""
    p = tmp_path / "carla.dbc"
    p.write_text(MINIMAL_DBC)
    return p


# ---------------------------------------------------------------------------
# Positive tests
# ---------------------------------------------------------------------------


def test_valid_dbc_loads_successfully(valid_dbc):
    """load_and_validate succeeds on a well-formed DBC with all required messages."""
    db, cycle_times = load_and_validate(valid_dbc)
    assert db is not None
    assert isinstance(cycle_times, dict)
    assert set(cycle_times.keys()) == {
        "THROTTLE", "BRAKE", "STEER",
        "REVERSE", "HAND_BRAKE", "MANUAL_TRANSMISSION", "GEAR",
    }


def test_cycle_times_converted_from_ms_to_seconds(valid_dbc):
    """GenMsgCycleTime values stored as milliseconds must be returned as seconds."""
    _, cycle_times = load_and_validate(valid_dbc)
    assert cycle_times["THROTTLE"]            == pytest.approx(0.1)   # 100 ms
    assert cycle_times["BRAKE"]               == pytest.approx(0.1)   # 100 ms
    assert cycle_times["STEER"]               == pytest.approx(0.1)   # 100 ms
    assert cycle_times["REVERSE"]             == pytest.approx(0.2)   # 200 ms
    assert cycle_times["HAND_BRAKE"]          == pytest.approx(0.2)   # 200 ms
    assert cycle_times["MANUAL_TRANSMISSION"] == pytest.approx(0.5)   # 500 ms
    assert cycle_times["GEAR"]                == pytest.approx(0.2)   # 200 ms


def test_unhandled_message_in_dbc_does_not_raise(tmp_path):
    """A DBC with an extra unknown message must be accepted; the entry is ignored."""
    extra_block = (
        '\nBO_ 100 UNKNOWN_MSG: 4 ECU\n'
        ' SG_ UNKNOWN_sig : 0|8@1+ (1,0) [0|255] "" ECU\n'
    )
    p = tmp_path / "extra.dbc"
    p.write_text(MINIMAL_DBC + extra_block)
    db, _ = load_and_validate(p)  # must not raise
    assert any(m.name == "UNKNOWN_MSG" for m in db.messages)


def test_zero_cycle_time_does_not_raise(tmp_path):
    """Required messages with GenMsgCycleTime=0 are valid; cycle_times is empty."""
    # Strip BA_ cycle time values so every message inherits the 0 ms default.
    no_ba = "\n".join(
        line for line in MINIMAL_DBC.splitlines()
        if not line.startswith('BA_ "GenMsgCycleTime"')
    )
    p = tmp_path / "no_cycle.dbc"
    p.write_text(no_ba)
    _, cycle_times = load_and_validate(p)
    assert cycle_times == {}


# ---------------------------------------------------------------------------
# Negative tests — each required message must be individually enforced
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing_msg", sorted(REQUIRED_MESSAGES))
def test_missing_required_message_raises_value_error(tmp_path, missing_msg):
    """Removing any required message from the DBC raises ValueError naming the message."""
    lines = MINIMAL_DBC.splitlines()
    filtered = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("BO_") and f" {missing_msg}:" in lines[i]:
            i += 2  # skip "BO_ ..." and " SG_ ..."
        else:
            filtered.append(lines[i])
            i += 1

    p = tmp_path / f"missing_{missing_msg}.dbc"
    p.write_text("\n".join(filtered))
    with pytest.raises(ValueError, match=missing_msg):
        load_and_validate(p)


def test_wrong_signal_name_raises_value_error(tmp_path):
    """A supported message whose signal has the wrong name raises ValueError."""
    broken = MINIMAL_DBC.replace("THROTTLE_signal", "WRONG_signal")
    p = tmp_path / "wrong_signal.dbc"
    p.write_text(broken)
    with pytest.raises(ValueError, match="THROTTLE"):
        load_and_validate(p)


def test_multiple_signals_raises_value_error(tmp_path):
    """A supported message with more than one signal raises ValueError."""
    broken = MINIMAL_DBC.replace(
        ' SG_ THROTTLE_signal : 0|8@1+ (1,0) [0|255] "" ECU\n',
        ' SG_ THROTTLE_signal : 0|8@1+ (1,0) [0|255] "" ECU\n'
        ' SG_ EXTRA_signal    : 8|8@1+ (1,0) [0|255] "" ECU\n',
    )
    p = tmp_path / "multi_signal.dbc"
    p.write_text(broken)
    with pytest.raises(ValueError, match="THROTTLE"):
        load_and_validate(p)


# ---------------------------------------------------------------------------
# Sensor message tests
# ---------------------------------------------------------------------------


@pytest.fixture
def sensor_dbc(tmp_path):
    """Temporary DBC file with all control messages and the 6 sensor messages."""
    p = tmp_path / "sensor.dbc"
    p.write_text(SENSOR_DBC)
    return p


def test_sensor_messages_in_supported_messages():
    """All SENSOR_MESSAGES names must be part of SUPPORTED_MESSAGES."""
    for name in SENSOR_MESSAGES:
        assert name in SUPPORTED_MESSAGES, f"{name} missing from SUPPORTED_MESSAGES"


def test_sensor_messages_load_without_error(sensor_dbc):
    """A DBC with multi-signal sensor messages must load without raising ValueError."""
    db, _ = load_and_validate(sensor_dbc)
    assert db is not None


def test_sensor_periodic_messages_in_cycle_times(sensor_dbc):
    """GNSS and IMU messages have non-zero cycle times and must appear in cycle_times."""
    _, cycle_times = load_and_validate(sensor_dbc)
    assert cycle_times["GNSS"]        == pytest.approx(1.0)    # 1000 ms
    assert cycle_times["IMU_ACCEL"]   == pytest.approx(0.1)    # 100 ms
    assert cycle_times["IMU_GYRO"]    == pytest.approx(0.1)
    assert cycle_times["IMU_COMPASS"] == pytest.approx(0.1)


def test_sensor_event_messages_absent_from_cycle_times(sensor_dbc):
    """COLLISION, LANE_INVASION and RADAR_TARGET have cycle_time=0 and must not appear in cycle_times."""
    _, cycle_times = load_and_validate(sensor_dbc)
    assert "COLLISION"     not in cycle_times
    assert "LANE_INVASION" not in cycle_times
    assert "RADAR_TARGET"  not in cycle_times


def test_sensor_message_with_missing_signal_raises_value_error(tmp_path):
    """Removing a declared signal from a sensor message raises ValueError."""
    broken = SENSOR_DBC.replace(
        ' SG_ GNSS_LON_signal : 32|32@1- (0.0000001,0) [-180|180] "deg" ECU\n',
        '',
    )
    p = tmp_path / "missing_sensor_signal.dbc"
    p.write_text(broken)
    with pytest.raises(ValueError, match="GNSS"):
        load_and_validate(p)
