import json
import sys
import time

import joblib
import numpy as np


class MlIntrusionDetection:
    """Isolation Forest IDS that flags CAN messages deviating from a trained normal-traffic baseline."""

    def __init__(self):
        self.model = None
        self.intrusion_counter = 0
        self.regular_counter = 0
        self._last_line_count = 0
        self._last_print_time = 0.0

    def load(self, path):
        """Load a trained Isolation Forest model from a PKL file."""
        self.model = joblib.load(path)
        print(f"[ML-IDS] Model loaded from: {path}")

    def run(self, msg):
        """Evaluate a single CAN message. Predicts -1 (anomaly) or 1 (normal)."""
        data = list(msg.data) + [0] * 8
        feature_vector = np.array([[msg.arbitration_id] + data[:8]])

        prediction = self.model.predict(feature_vector)[0]

        if prediction == -1:
            self.intrusion_counter += 1
            self._print_results(alert=True)
        else:
            self.regular_counter += 1
            self._print_results(alert=False)

    def _print_results(self, alert: bool):
        now = time.monotonic()
        if not alert and (now - self._last_print_time) < 0.1:
            return
        self._last_print_time = now

        RESET  = "\033[0m"
        RED    = "\033[91m"
        CYAN   = "\033[96m"
        DIM    = "\033[2m"
        SEP    = DIM + "─" * 44 + RESET

        alert_tag = f"  {RED}[ALERT]{RESET}" if alert else ""

        lines = [
            SEP,
            f"Regular messages : {CYAN}{self.regular_counter}{RESET}",
            f"Total intrusions : {(RED if self.intrusion_counter else CYAN)}{self.intrusion_counter}{RESET}{alert_tag}",
            SEP,
        ]

        if self._last_line_count > 0:
            sys.stdout.write(f"\033[{self._last_line_count}A")
            for _ in range(self._last_line_count):
                sys.stdout.write("\033[2K\n")
            sys.stdout.write(f"\033[{self._last_line_count}A")

        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()
        self._last_line_count = len(lines)
