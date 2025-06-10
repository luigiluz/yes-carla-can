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
    def __init__(self):
        self.intrusion_counter = {}
        self.regular_counter = 0

    def load(self, path=None):
        # Load json file
        with open(path, 'r') as f:
            can_ids_statistics = json.load(f)

        self.known_ids = list(can_ids_statistics.keys())
        print(f"self.known_ids = {self.known_ids}")
        self.can_ids_statistics = can_ids_statistics
        self.running_statistics = {}

    def run(self, message):
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
        if id:
            print("Intrusion detection based on CAN ID!", flush=True)
        if time:
            print("Intrusion detection based on time!", flush=True)
        print(f"Total intrusions: {json.dumps(self.intrusion_counter, indent=2)}", flush=True)
        print(f"Regular messages: {self.regular_counter}", flush=True)
        sys.stdout.flush()  # Extra guarantee for flushing
