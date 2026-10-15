import datetime
import os
import threading
import time
from collections import deque

import can
import pygame

from can_network.bus_config import VCAN_CHANNEL, bus_kwargs
from defense.id_time_intrusion_detection import IdTimeIntrusionDetection
from defense.ids_training.ml_intrusion_detection import MlIntrusionDetection


class IntrusionDetectionPanel:
    """Renders the IDS as a live, toggleable panel stacked alongside the CAN traffic
    panels. Hosts two detectors - the time-based IDS (ID + inter-arrival time) and the
    Isolation Forest IDS (ID + payload) - and runs one at a time; the bound keys (see
    gui/keyboard_control.py) arm/disarm it and cycle between them, so an attack can be
    demonstrated with and without detection, and with each detector. Starts disabled.
    While disabled, frames are never passed to the detector, so its internal timing
    state stays frozen rather than drifting stale.

    The Isolation Forest costs ~3.6 ms per single-frame predict() but ~5 ms for a batch
    of 1000, so its frames are queued and scored in batches on a worker thread instead
    of inline - inline scoring can't keep up with the bus and would stall the main loop
    on the neovi backend, where feed() is called from it.
    """

    PANEL_WIDTH = 480
    PADDING = 8
    LINE_HEIGHT = 22
    COLOR_BG = (0, 0, 0)
    COLOR_TEXT = (255, 214, 150)
    COLOR_DIVIDER_ACCENT = (255, 176, 32)
    COLOR_ALERT = (255, 82, 87)
    COLOR_WARN = (255, 176, 32)
    COLOR_INFO = (140, 150, 145)
    COLOR_ON = (41, 224, 138)
    COLOR_OFF = (120, 120, 120)

    ML_BATCH_INTERVAL = 0.05
    ML_QUEUE_MAX = 20000

    def __init__(self, stats_path, model_path=None, powertrain_channel=VCAN_CHANNEL, comfort_channel=None,
                 serial: str = None, passive: bool = False, max_alerts: int = 8):
        """passive=True: don't open any bus of our own - the caller feeds frames via
        feed(), e.g. a SharedPhysicalBus that already owns the one allowed handle to
        the physical device. passive=False (socketcan/vcan): open our own read-only
        bus(es), same reasoning as CANTrafficDisplay - the kernel allows multiple
        sockets per vcan interface, so no sharing is needed."""
        time_based = IdTimeIntrusionDetection()
        time_based.load(stats_path)
        self._detectors = [("Time-Based", time_based)]
        if model_path and os.path.exists(model_path):
            ml = MlIntrusionDetection()
            ml.load(model_path)
            self._detectors.append(("Isolation Forest", ml))
        else:
            print(f"[IntrusionDetectionPanel] No Isolation Forest model at {model_path} - only Time-Based IDS available")
        self._index = 0
        self._ml_queue = deque(maxlen=self.ML_QUEUE_MAX)

        self.enabled = False
        self._alerts = deque(maxlen=max_alerts)
        self._lock = threading.Lock()
        self._font = None
        self._passive = passive
        self._active = True
        self._threads = []
        self._buses = []

        if len(self._detectors) > 1:
            thread = threading.Thread(target=self._ml_loop, daemon=True)
            self._threads.append(thread)
            thread.start()

        if passive:
            return

        channels = {powertrain_channel, comfort_channel} - {None}
        for channel in channels:
            try:
                bus = can.Bus(**bus_kwargs(channel, serial=serial))
            except Exception as exc:
                print(f"[IntrusionDetectionPanel] Could not open {channel}: {exc}")
                continue
            self._buses.append(bus)
            thread = threading.Thread(target=self._recv_loop, args=(bus,), daemon=True)
            self._threads.append(thread)
            thread.start()

    def _recv_loop(self, bus):
        while self._active:
            try:
                msg = bus.recv(timeout=1.0)
                if msg is not None:
                    self.feed(msg)
            except can.CanOperationError:
                break
            except Exception:
                break

    @property
    def name(self):
        return self._detectors[self._index][0]

    @property
    def _detector(self):
        return self._detectors[self._index][1]

    def _ml_loop(self):
        while self._active:
            time.sleep(self.ML_BATCH_INTERVAL)
            msgs = []
            while self._ml_queue:
                msgs.append(self._ml_queue.popleft())
            if not msgs:
                continue
            with self._lock:
                if not self.enabled or not isinstance(self._detector, MlIntrusionDetection):
                    continue
                for msg in self._detector.run_batch(msgs):
                    id_hex = format(msg.arbitration_id, 'X')
                    self._alerts.append((msg.timestamp, self.COLOR_ALERT, f"[ALERT] anomaly on {id_hex}"))

    def feed(self, msg):
        """Passive mode: called by whoever owns the shared bus for each frame on our
        channel. Active mode: called from our own _recv_loop thread."""
        if not self.enabled:
            return
        if isinstance(self._detector, MlIntrusionDetection):
            self._ml_queue.append(msg)
            return

        id_hex = format(msg.arbitration_id, 'X')
        with self._lock:
            before_intr = self._detector.intrusion_counter.get(id_hex, 0)

            self._detector.run(msg)

            ts = msg.timestamp
            if self._detector.intrusion_counter.get(id_hex, 0) != before_intr:
                if id_hex in self._detector.known_ids:
                    text = f"[ALERT] timing anomaly on {id_hex}"
                else:
                    text = f"[ALERT] unknown CAN ID {id_hex}"
                self._alerts.append((ts, self.COLOR_ALERT, text))

    def toggle(self):
        with self._lock:
            self.enabled = not self.enabled
            if self.enabled:
                # Clean slate for each arm-cycle, without re-loading the baseline/model.
                self._detector.reset()
                self._alerts.clear()
                self._ml_queue.clear()
            return self.enabled

    def cycle(self):
        """Switch to the next detector, starting it from a clean slate. Returns its name."""
        with self._lock:
            self._index = (self._index + 1) % len(self._detectors)
            self._detector.reset()
            self._alerts.clear()
            self._ml_queue.clear()
            return self.name

    def stop(self):
        self._active = False
        for bus in self._buses:
            bus.shutdown()
        for thread in self._threads:
            thread.join(timeout=2.0)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _init_font(self):
        if self._font is not None:
            return
        fonts = [x for x in pygame.font.get_fonts() if "mono" in x]
        preferred = "ubuntumono"
        name = preferred if preferred in fonts else (fonts[0] if fonts else None)
        if name:
            self._font = pygame.font.Font(pygame.font.match_font(name), 18)
        else:
            self._font = pygame.font.Font(pygame.font.get_default_font(), 17)

    def render(self, display: pygame.Surface, slot: int = 2, total_slots: int = 3):
        self._init_font()
        screen_w, screen_h = display.get_size()
        panel_gap = 12
        panel_x = screen_w - self.PANEL_WIDTH
        panel_height = (screen_h - panel_gap * (total_slots - 1)) // total_slots
        panel_y = slot * (panel_height + panel_gap)

        bg = pygame.Surface((self.PANEL_WIDTH, panel_height), pygame.SRCALPHA)
        bg.fill((*self.COLOR_BG, 140))
        display.blit(bg, (panel_x, panel_y))

        pygame.draw.rect(
            display, self.COLOR_DIVIDER_ACCENT, (panel_x, panel_y, self.PANEL_WIDTH, panel_height), 1
        )

        header_surf = self._font.render(f"IDS: {self.name}", True, self.COLOR_DIVIDER_ACCENT)
        display.blit(header_surf, (panel_x + self.PADDING, panel_y + self.PADDING))

        pill_text = "ENABLED" if self.enabled else "DISABLED"
        pill_color = self.COLOR_ON if self.enabled else self.COLOR_OFF
        pill_surf = self._font.render(pill_text, True, pill_color)
        display.blit(pill_surf, (panel_x + self.PANEL_WIDTH - pill_surf.get_width() - self.PADDING,
                                  panel_y + self.PADDING))

        divider_y = panel_y + self.PADDING + self.LINE_HEIGHT + 2
        pygame.draw.line(
            display, self.COLOR_DIVIDER_ACCENT,
            (panel_x, divider_y), (panel_x + self.PANEL_WIDTH, divider_y), 1,
        )

        y = divider_y + 4
        panel_bottom = panel_y + panel_height - self.LINE_HEIGHT

        hint_surf = self._font.render("I arm/disarm   U switch IDS", True, self.COLOR_INFO)
        display.blit(hint_surf, (panel_x + self.PADDING, panel_bottom))

        with self._lock:
            total_intrusions = sum(self._detector.intrusion_counter.values())
            regular_count = self._detector.regular_counter
            alerts_snapshot = list(self._alerts)
        summary = f"Regular {regular_count}   Intrusions {total_intrusions}"
        summary_color = self.COLOR_ALERT if total_intrusions else self.COLOR_TEXT
        surf = self._font.render(summary, True, summary_color)
        display.blit(surf, (panel_x + self.PADDING, y))
        y += self.LINE_HEIGHT

        pygame.draw.line(
            display, self.COLOR_DIVIDER_ACCENT,
            (panel_x, y), (panel_x + self.PANEL_WIDTH, y), 1,
        )
        y += 4

        visible_lines = max(0, (panel_bottom - y) // self.LINE_HEIGHT)
        for ts, color, text in reversed(alerts_snapshot[-visible_lines:]):
            if y + self.LINE_HEIGHT > panel_bottom:
                break
            ts_text = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S.%f")[:-3]
            surf = self._font.render(f"{ts_text}  {text}", True, color)
            display.blit(surf, (panel_x + self.PADDING, y))
            y += self.LINE_HEIGHT
