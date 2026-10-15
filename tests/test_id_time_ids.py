"""Tests for the time-based (ID + inter-arrival time) intrusion detector."""
import json
import random

import can
import pytest

from defense.id_time_intrusion_detection import IdTimeIntrusionDetection

PERIOD = 0.1
JITTER_STD = 0.003


@pytest.fixture
def detector(tmp_path, monkeypatch):
    monkeypatch.setattr(IdTimeIntrusionDetection, "print_results", lambda self, **kwargs: None)
    stats = {"600": {"mean_timestamp_diff": PERIOD, "std_timestamp_diff": JITTER_STD, "msg_type": "periodic"}}
    stats_path = tmp_path / "stats.json"
    stats_path.write_text(json.dumps(stats))
    ids = IdTimeIntrusionDetection()
    ids.load(stats_path)
    return ids


def _frames(arbitration_id, timestamps):
    return [can.Message(arbitration_id=arbitration_id, timestamp=t) for t in timestamps]


def _regular_timestamps(count):
    rng = random.Random(0)
    return [i * PERIOD + rng.gauss(0, JITTER_STD / 2) for i in range(count)]


def test_regular_periodic_traffic_raises_no_intrusions(detector):
    for msg in _frames(0x600, _regular_timestamps(200)):
        detector.run(msg)

    assert detector.intrusion_counter == {}
    assert detector.regular_counter == 200


def test_injected_frames_are_flagged(detector):
    timestamps = _regular_timestamps(50)
    timestamps += [timestamps[-1] + PERIOD * k / 4 for k in range(1, 20)]
    for msg in _frames(0x600, timestamps):
        detector.run(msg)

    assert detector.intrusion_counter.get("600", 0) > 0


def test_unknown_id_is_flagged(detector):
    detector.run(can.Message(arbitration_id=0x7FF, timestamp=0.0))

    assert detector.intrusion_counter == {"7FF": 1}
