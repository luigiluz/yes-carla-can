"""Tests for the Isolation Forest intrusion detector with per-ID thresholds."""
import random

import can
import joblib
import numpy as np
import pytest
from sklearn.ensemble import IsolationForest

from defense.ids_training.ml_intrusion_detection import MlIntrusionDetection


@pytest.fixture
def detector(tmp_path):
    # Normal traffic: 604 (hand brake) always 00, 600 (throttle) a varying 4-byte value.
    rng = random.Random(0)
    X = np.array(
        [[0x604, 0, 0, 0, 0, 0, 0, 0, 0] for _ in range(300)]
        + [[0x600, rng.randrange(256), rng.randrange(256), 0, 0, 0, 0, 0, 0] for _ in range(300)]
    )
    model = IsolationForest(random_state=42).fit(X)
    scores = model.score_samples(X)
    thresholds = {format(i, "X"): float(scores[X[:, 0] == i].min()) - 1e-6 for i in (0x604, 0x600)}
    path = tmp_path / "model.pkl"
    joblib.dump({"model": model, "thresholds": thresholds, "excluded_ids": ["611"]}, path)

    ids = MlIntrusionDetection()
    ids.load(path)
    return ids


def test_normal_frames_are_not_flagged(detector):
    msgs = [can.Message(arbitration_id=0x604, data=[0])] * 50
    msgs += [can.Message(arbitration_id=0x600, data=[10, 200, 0, 0])] * 50

    assert detector.run_batch(msgs) == []
    assert detector.regular_counter == 100


def test_spoofed_payload_is_flagged_with_its_id(detector):
    spoofed = can.Message(arbitration_id=0x604, data=[1])

    assert detector.run_batch([spoofed]) == [spoofed]
    assert detector.intrusion_counter == {"604": 1}


def test_unknown_id_is_flagged_and_excluded_id_is_not(detector):
    unknown = can.Message(arbitration_id=0x7FF, data=[0])
    excluded = can.Message(arbitration_id=0x611, data=[255] * 8)

    assert detector.run_batch([unknown, excluded]) == [unknown]


def test_reset_clears_counters(detector):
    detector.run_batch([can.Message(arbitration_id=0x604, data=[1])])
    detector.reset()

    assert detector.intrusion_counter == {}
    assert detector.regular_counter == 0
