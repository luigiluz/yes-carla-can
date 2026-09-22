import threading
from collections import deque

import can
import pygame

from can_network.bus_config import VCAN_CHANNEL, bus_kwargs
from defense.phase_lock_intrusion_detection import PhaseLockIntrusionDetection


class IntrusionDetectionPanel:
    """Renders the phase-lock IDS as a live, toggleable panel stacked alongside the
    CAN traffic panels. Starts disabled - press the bound key (see
    gui/keyboard_control.py) to arm it, so an attack can be demonstrated with and
    without detection active. While disabled, frames are never passed to the
    detector, so its internal timing state stays frozen rather than drifting stale.
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

    def __init__(self, dbc_path, powertrain_channel=VCAN_CHANNEL, comfort_channel=None,
                 serial: str = None, passive: bool = False, max_alerts: int = 8):
        """passive=True: don't open any bus of our own - the caller feeds frames via
        feed(), e.g. a SharedPhysicalBus that already owns the one allowed handle to
        the physical device. passive=False (socketcan/vcan): open our own read-only
        bus(es), same reasoning as CANTrafficDisplay - the kernel allows multiple
        sockets per vcan interface, so no sharing is needed."""
        self._dbc_path = dbc_path
        self._detector = PhaseLockIntrusionDetection()
        self._detector.load(dbc_path)

        self.enabled = False
        self._alerts = deque(maxlen=max_alerts)
        self._lock = threading.Lock()
        self._font = None
        self._passive = passive
        self._active = True
        self._threads = []
        self._buses = []

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

    def feed(self, msg):
        """Passive mode: called by whoever owns the shared bus for each frame on our
        channel. Active mode: called from our own _recv_loop thread."""
        if not self.enabled:
            return

        id_hex = format(msg.arbitration_id, 'X')
        with self._lock:
            before_intr = self._detector.intrusion_counter.get(id_hex, 0)
            before_miss = self._detector.missed_counter.get(id_hex, 0)

            self._detector.run(msg)

            ts = msg.timestamp
            if self._detector.intrusion_counter.get(id_hex, 0) != before_intr:
                self._alerts.append((ts, self.COLOR_ALERT, f"[ALERT] injected/early frame on {id_hex}"))
            elif self._detector.missed_counter.get(id_hex, 0) != before_miss:
                self._alerts.append((ts, self.COLOR_WARN, f"[WARN] missed cycle on {id_hex}"))

    def toggle(self):
        with self._lock:
            self.enabled = not self.enabled
            if self.enabled:
                # Clean slate for each arm-cycle, without re-parsing the DBC.
                self._detector.tracking = {}
                self._detector.intrusion_counter = {}
                self._detector.missed_counter = {}
                self._detector.regular_counter = 0
                self._alerts.clear()
            return self.enabled

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

        header_surf = self._font.render("Phase-Lock IDS", True, self.COLOR_DIVIDER_ACCENT)
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
        panel_bottom = panel_y + panel_height

        with self._lock:
            total_intrusions = sum(self._detector.intrusion_counter.values())
            total_missed = sum(self._detector.missed_counter.values())
            regular_count = self._detector.regular_counter
            alerts_snapshot = list(self._alerts)
        summary = (
            f"Regular {regular_count}   "
            f"Intrusions {total_intrusions}   Missed {total_missed}"
        )
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
        for _, color, text in reversed(alerts_snapshot[-visible_lines:]):
            if y + self.LINE_HEIGHT > panel_bottom:
                break
            surf = self._font.render(text, True, color)
            display.blit(surf, (panel_x + self.PADDING, y))
            y += self.LINE_HEIGHT
