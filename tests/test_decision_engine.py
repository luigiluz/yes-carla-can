"""Tests for the decision engine stub (camera -> decision engine -> vehicle controls)."""
from decision_engine import DecisionEngine


def test_apply_is_pass_through():
    engine = DecisionEngine()
    control = object()
    assert engine.apply(control) is control


def test_on_ts_data_updates_stats():
    engine = DecisionEngine()
    engine.on_ts_data(b"\x47" * 188)
    engine.on_ts_data(b"\x47" * 376)
    stats = engine.stats
    assert stats["chunks_received"] == 2
    assert stats["bytes_received"] == 564
    assert stats["last_data_time"] is not None
