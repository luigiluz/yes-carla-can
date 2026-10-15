import json
import sys
import time

import joblib
import numpy as np


class MlIntrusionDetection:
    """Isolation Forest IDS that flags CAN messages deviating from a trained normal-traffic baseline."""

    def __init__(self):
        self.model = None
        self.thresholds = None
        self.excluded_ids = set()
        self.intrusion_counter = {}
        self.regular_counter = 0
        self._last_alert_id = None
        self._last_line_count = 0
        self._last_print_time = 0.0

    def load(self, path):
        """Load a trained Isolation Forest from a PKL file - either a bundle written by train.py
        ({"model", "thresholds", "excluded_ids"}) or a bare model from older trainings."""
        loaded = joblib.load(path)
        if isinstance(loaded, dict):
            self.model = loaded["model"]
            self.thresholds = loaded["thresholds"]
            self.excluded_ids = set(loaded.get("excluded_ids", []))
        else:
            self.model = loaded
        print(f"[ML-IDS] Model loaded from: {path}")

    def reset(self):
        """Clear counters, keeping the loaded model."""
        self.intrusion_counter = {}
        self.regular_counter = 0
        self._last_alert_id = None

    @staticmethod
    def _features(msg):
        data = list(msg.data) + [0] * 8
        return [msg.arbitration_id] + data[:8]

    def run_batch(self, msgs):
        """Evaluate several CAN messages with one predict() call - far cheaper per frame
        than predicting one at a time. Returns the anomalous messages, in order."""
        if not msgs:
            return []
        features = np.array([self._features(m) for m in msgs])
        if self.thresholds is None:
            is_anomaly = self.model.predict(features) == -1
        else:
            # Per-ID cutoffs; IDs never seen in training count as anomalies, excluded IDs never do
            scores = self.model.score_samples(features)
            is_anomaly = [
                format(m.arbitration_id, 'X') not in self.excluded_ids
                and score < self.thresholds.get(format(m.arbitration_id, 'X'), np.inf)
                for m, score in zip(msgs, scores)
            ]

        anomalous = []
        for msg, anomaly in zip(msgs, is_anomaly):
            if anomaly:
                id = format(msg.arbitration_id, 'X')
                self.intrusion_counter[id] = self.intrusion_counter.get(id, 0) + 1
                self._last_alert_id = id
                anomalous.append(msg)
            else:
                self.regular_counter += 1
        return anomalous

    def run(self, msg):
        """Evaluate a single CAN message. Predicts -1 (anomaly) or 1 (normal)."""
        alert = bool(self.run_batch([msg]))
        self._print_results(alert=alert)

    def _print_results(self, alert: bool):
        now = time.monotonic()
        if not alert and (now - self._last_print_time) < 0.1:
            return
        self._last_print_time = now

        RESET  = "\033[0m"
        RED    = "\033[91m"
        YELLOW = "\033[93m"
        CYAN   = "\033[96m"
        DIM    = "\033[2m"
        SEP    = DIM + "─" * 44 + RESET

        lines = [SEP]
        if self._last_alert_id:
            lines.append(f"{RED}[ALERT] Anomaly detected on ID {self._last_alert_id}{RESET}")
        lines.append(f"Regular messages : {CYAN}{self.regular_counter}{RESET}")
        total = sum(self.intrusion_counter.values())
        lines.append(f"Total intrusions : {(RED if total else CYAN)}{total}{RESET}")
        if self.intrusion_counter:
            lines.append(f"{YELLOW}Intrusion counts :{RESET}")
            for json_line in json.dumps(self.intrusion_counter, indent=2).splitlines():
                lines.append(f"  {json_line}")
        lines.append(SEP)

        if self._last_line_count > 0:
            sys.stdout.write(f"\033[{self._last_line_count}A")
            for _ in range(self._last_line_count):
                sys.stdout.write("\033[2K\n")
            sys.stdout.write(f"\033[{self._last_line_count}A")

        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()
        self._last_line_count = len(lines)
