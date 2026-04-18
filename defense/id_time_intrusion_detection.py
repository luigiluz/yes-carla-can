import json
import sys

from collections import deque
import math

class QueueStats:
    def __init__(self, maxlen=10):
        self.queue = deque(maxlen=maxlen)
        self._sum = 0
        self._sum_sq = 0

    def add(self, value):
        if len(self.queue) == self.queue.maxlen:
            old_value = self.queue[0]
            self._sum -= old_value
            self._sum_sq -= old_value * old_value
        self.queue.append(value)
        self._sum += value
        self._sum_sq += value * value

    def mean(self):
        if not self.queue:
            return 0
        return self._sum / len(self.queue)

    def std(self):
        if len(self.queue) < 2:
            return 0
        n = len(self.queue)
        mean = self._sum / n
        variance = (self._sum_sq / n) - (mean * mean)
        return math.sqrt(max(0, variance))  # max prevents floating point errors

    def get_values(self):
        return list(self.queue)

    def __len__(self):
        return len(self.queue)

class IdTimeIntrusionDetection():
    """Statistical IDS that flags CAN messages whose inter-arrival time deviates from a baseline."""

    def __init__(self):
        self.intrusion_counter = {}
        self.regular_counter = 0
        self._last_line_count = 0
        self._last_alert = ""

    def load(self, path=None):
        """Load baseline CAN ID timing statistics from a JSON file."""
        with open(path, 'r') as f:
            can_ids_statistics = json.load(f)

        self.known_ids = list(can_ids_statistics.keys())
        print(f"self.known_ids = {self.known_ids}")
        self.can_ids_statistics = can_ids_statistics
        self.running_statistics = {}

    def run(self, message):
        """Evaluate a single CAN message and update intrusion/regular counters."""
        id = str(hex(message.arbitration_id))
        timestamp = message.timestamp

        if id not in self.known_ids:
            if id not in self.intrusion_counter:
                self.intrusion_counter[id] = 1
            else:
                self.intrusion_counter[id] += 1
            self.print_results(id=True)
            return

        if self.can_ids_statistics[id]['msg_type'] == "periodic":
            if id not in self.running_statistics:
                self.running_statistics[id] = {'last_timestamps': QueueStats(maxlen=10)}
                self.running_statistics[id]['last_timestamps'].add(timestamp)
            else:
                self.running_statistics[id]['last_timestamps'].add(timestamp)

            # Check if queue is full
            if len(self.running_statistics[id]['last_timestamps']) == self.running_statistics[id]['last_timestamps'].queue.maxlen:
                expected_std = 3*self.can_ids_statistics[id]["std_timestamp_diff"]
                actual_std = self.running_statistics[id]['last_timestamps'].std()
                # Take the mean value of the queue
                #actual_diff = self.running_statistics[id]['last_timestamps'].mean() - self.can_ids_statistics[id]["mean_timestamp_diff"]

                self.running_statistics[id]['last_timestamps'].add(timestamp)

                if actual_std > expected_std:
                    if id not in self.intrusion_counter:
                        self.intrusion_counter[id] = 1
                    else:
                        self.intrusion_counter[id] += 1
                    self.print_results(time=True)
                    return

        self.regular_counter += 1
        self.print_results()

    def print_results(self, id: bool = False, time: bool = False):
        RESET  = "\033[0m"
        RED    = "\033[91m"
        YELLOW = "\033[93m"
        CYAN   = "\033[96m"
        DIM    = "\033[2m"
        SEP    = DIM + "─" * 44 + RESET

        if id:
            self._last_alert = f"{RED}[ALERT] Unknown CAN ID detected{RESET}"
        elif time:
            self._last_alert = f"{RED}[ALERT] Timing anomaly detected{RESET}"

        lines = [SEP]
        if self._last_alert:
            lines.append(self._last_alert)
        lines.append(
            f"Regular messages : {CYAN}{self.regular_counter}{RESET}"
        )
        total = sum(self.intrusion_counter.values())
        lines.append(
            f"Total intrusions : {(RED if total else CYAN)}{total}{RESET}"
        )
        if self.intrusion_counter:
            lines.append(f"{YELLOW}Intrusion counts :{RESET}")
            for json_line in json.dumps(self.intrusion_counter, indent=2).splitlines():
                lines.append(f"  {json_line}")
        lines.append(SEP)

        # Overwrite the previous block in-place
        if self._last_line_count > 0:
            sys.stdout.write(f"\033[{self._last_line_count}A")
            for _ in range(self._last_line_count):
                sys.stdout.write("\033[2K\n")
            sys.stdout.write(f"\033[{self._last_line_count}A")

        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()
        self._last_line_count = len(lines)
