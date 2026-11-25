"""
decision_engine.py — Camera → [Decision Engine] → Vehicle Controls
=================================================================

Sits between the AVTP camera stream and the CAN vehicle controls:

    CARLA camera ──AVTP──► AvtpReceiver ──on_ts_data()──► DecisionEngine
                                                               │
    keyboard ──► KeyboardSenderControl ──apply(control)────────┘──► CAN bus

Right now this is a pass-through stub: it only keeps track of the video data
it receives and returns the driver's control unchanged. Future perception and
decision logic (e.g. decode frames with PyAV, detect obstacles, and adjust
throttle/brake/steer) belongs here.

Threading: ``on_ts_data`` is called from the AVTP receiver thread, while
``apply`` is called from the vehicle controls (pygame) main loop, so shared
state is guarded by a lock.
"""
from __future__ import annotations

import threading
import time


class DecisionEngine:
    def __init__(self):
        self._lock = threading.Lock()
        self._latest_ts: bytes | None = None
        self._bytes_received = 0
        self._chunks_received = 0
        self._last_data_time: float | None = None

    # ── Input: video stream (receiver thread) ────────────────────────────────

    def on_ts_data(self, data: bytes) -> None:
        """Receive one chunk of MPEG-TS data from the AVTP receiver."""
        with self._lock:
            self._latest_ts = data
            self._bytes_received += len(data)
            self._chunks_received += 1
            self._last_data_time = time.time()

    # ── Output: vehicle control (main loop) ──────────────────────────────────

    def apply(self, control):
        """
        Return the control to send over CAN, given the driver's ``control``
        (a ``carla.VehicleControl``). Currently a pass-through.
        """
        return control

    # ── Introspection ────────────────────────────────────────────────────────

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "chunks_received": self._chunks_received,
                "bytes_received": self._bytes_received,
                "last_data_time": self._last_data_time,
            }
