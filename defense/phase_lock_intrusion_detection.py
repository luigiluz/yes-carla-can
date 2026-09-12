import json
import sys
from time import monotonic as time_monotonic

import cantools


class PhaseLockIntrusionDetection():
    """Phase-locked periodicity IDS.

    For each CAN ID with a declared DBC cycle time, predicts the next arrival
    slot from the *last accepted* frame (not merely the last received frame).
    A frame that arrives well before its predicted slot is flagged as a
    suspected injected/spoofed frame, but the anchor is left untouched — so
    the next genuine frame is still judged against its own true slot instead
    of inheriting the anomaly from the injected one.
    """

    CALIBRATION_SAMPLES = 20
    UNRELIABLE_DEVIATION_RATIO = 0.5
    SIGMA_MULTIPLIER = 8
    MIN_WINDOW = 0.003
    EWMA_ALPHA = 0.1
    PERIOD_DRIFT_CLIP = 0.5

    def __init__(self):
        self.intrusion_counter = {}
        self.missed_counter = {}
        self.regular_counter = 0
        self.tracking = {}
        self._last_line_count = 0
        self._last_alert = ""
        self._last_print_time = 0.0

    def load(self, dbc_path=None):
        """Load per-ID declared periods (GenMsgCycleTime) from a DBC file."""
        db = cantools.database.load_file(dbc_path)
        self.id_periods = {}
        for msg in db.messages:
            if msg.cycle_time:
                self.id_periods[format(msg.frame_id, 'X')] = msg.cycle_time / 1000.0
        print(f"[phase_lock] Loaded {len(self.id_periods)} periodic CAN IDs from {dbc_path}")

    def run(self, message):
        """Evaluate a single CAN message and update intrusion/regular counters."""
        id = format(message.arbitration_id, 'X')
        timestamp = message.timestamp

        if id not in self.id_periods:
            self.regular_counter += 1
            self.print_results()
            return

        state = self.tracking.get(id)
        if state is None:
            declared = self.id_periods[id]
            state = self.tracking[id] = {
                "phase": "calibrating",
                "calib_deltas": [],
                "last_time": None,
                "last_accepted_time": None,
                "t_est": declared,
                "sigma_est": declared * 0.1,
            }

        if state["phase"] == "unreliable":
            self.regular_counter += 1
            self.print_results()
        elif state["phase"] == "calibrating":
            self._calibrate(id, state, timestamp)
        else:
            self._track_locked(id, state, timestamp)

    def _calibrate(self, id, state, timestamp):
        """Learn the real inter-arrival period/jitter before enforcing anything.

        Some DBC-declared cycle times don't match reality (e.g. sensor IDs
        ticking at simulation rate rather than their declared period) -
        trusting them blindly would flag almost every real frame as early.
        """
        if state["last_time"] is not None:
            state["calib_deltas"].append(timestamp - state["last_time"])
        state["last_time"] = timestamp

        if len(state["calib_deltas"]) < self.CALIBRATION_SAMPLES:
            self.regular_counter += 1
            self.print_results()
            return

        deltas = state["calib_deltas"]
        mean = sum(deltas) / len(deltas)
        variance = sum((d - mean) ** 2 for d in deltas) / len(deltas)
        sigma = variance ** 0.5

        declared = self.id_periods[id]
        deviation = abs(mean - declared) / declared if declared else 1.0

        if deviation > self.UNRELIABLE_DEVIATION_RATIO:
            state["phase"] = "unreliable"
            self.regular_counter += 1
            self.print_results(unreliable=id)
            return

        state["phase"] = "locked"
        state["t_est"] = mean
        state["sigma_est"] = sigma
        state["last_accepted_time"] = timestamp
        self.regular_counter += 1
        self.print_results()

    def _track_locked(self, id, state, timestamp):
        declared = self.id_periods[id]
        window = max(self.SIGMA_MULTIPLIER * state["sigma_est"], self.MIN_WINDOW)
        expected_next = state["last_accepted_time"] + state["t_est"]

        if timestamp < expected_next - window:
            self.intrusion_counter[id] = self.intrusion_counter.get(id, 0) + 1
            self.print_results(early=id)
            return

        delta = timestamp - state["last_accepted_time"]
        if timestamp > expected_next + window:
            self.missed_counter[id] = self.missed_counter.get(id, 0) + 1

        state["last_accepted_time"] = timestamp
        low, high = declared * (1 - self.PERIOD_DRIFT_CLIP), declared * (1 + self.PERIOD_DRIFT_CLIP)
        new_t_est = (1 - self.EWMA_ALPHA) * state["t_est"] + self.EWMA_ALPHA * delta
        state["t_est"] = min(max(new_t_est, low), high)
        state["sigma_est"] = (1 - self.EWMA_ALPHA) * state["sigma_est"] + self.EWMA_ALPHA * abs(delta - state["t_est"])

        self.regular_counter += 1
        self.print_results()

    def print_results(self, early: str = None, missed: str = None, unreliable: str = None):
        RESET  = "\033[0m"
        RED    = "\033[91m"
        YELLOW = "\033[93m"
        CYAN   = "\033[96m"
        DIM    = "\033[2m"
        SEP    = DIM + "─" * 44 + RESET

        if early:
            self._last_alert = f"{RED}[ALERT] Injected/early frame detected on ID {early}{RESET}"
        elif missed:
            self._last_alert = f"{YELLOW}[WARN] Missed cycle detected on ID {missed}{RESET}"
        elif unreliable:
            self._last_alert = (
                f"{YELLOW}[INFO] ID {unreliable} declared period doesn't match observed "
                f"traffic - phase-lock disabled for this ID{RESET}"
            )

        is_alert = bool(early or missed or unreliable)
        now = time_monotonic()
        if not is_alert and (now - self._last_print_time) < 0.1:
            return
        self._last_print_time = now

        lines = [SEP]
        if self._last_alert:
            lines.append(self._last_alert)
        lines.append(f"Regular messages : {CYAN}{self.regular_counter}{RESET}")
        total = sum(self.intrusion_counter.values())
        lines.append(f"Total intrusions : {(RED if total else CYAN)}{total}{RESET}")
        if self.intrusion_counter:
            lines.append(f"{YELLOW}Intrusion counts :{RESET}")
            for json_line in json.dumps(self.intrusion_counter, indent=2).splitlines():
                lines.append(f"  {json_line}")
        total_missed = sum(self.missed_counter.values())
        lines.append(f"Missed cycles    : {(YELLOW if total_missed else CYAN)}{total_missed}{RESET}")
        lines.append(SEP)

        if self._last_line_count > 0:
            sys.stdout.write(f"\033[{self._last_line_count}A")
            for _ in range(self._last_line_count):
                sys.stdout.write("\033[2K\n")
            sys.stdout.write(f"\033[{self._last_line_count}A")

        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()
        self._last_line_count = len(lines)
