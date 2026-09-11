import datetime
import os
import threading
from collections import deque

import can
import pygame

from can_network.bus_config import VCAN_CHANNEL, bus_kwargs


class CANTrafficDisplay:
    """
    Renders a live CAN-traffic panel (candump-style) as a compact box in the
    top-right corner of the pygame display, stacked with any other panels via
    the `slot` argument to render(). Opens its own read-only bus on *vcan0* so
    it never interferes with the main CAN_Network bus.
    """

    PANEL_WIDTH = 480
    LINE_HEIGHT = 22
    PADDING = 8
    PANEL_GAP = 12
    COLOR_BG = (0, 0, 0)
    COLOR_HEADER = (0, 230, 100)
    COLOR_TEXT = (160, 255, 160)
    COLOR_DIVIDER = (0, 180, 80)

    def __init__(self, channel: str = VCAN_CHANNEL, serial: str = None, max_messages: int = 100,
                 passive: bool = False, log_path: str = None, accent: tuple = None):
        """passive=True: don't open a bus/thread of our own — the caller feeds frames via
        feed(), e.g. a SharedPhysicalBus that already owns the one allowed handle to this
        physical device. Used on the neovi backend, where opening yet another handle to
        the same device would fail.

        log_path: if given, every frame shown in the panel is also appended to this file
        in candump format (the extension picks the writer — see can.Logger), so traffic
        can be replayed/analyzed later. Useful on the neovi backend where candump itself
        can't attach to the device.

        accent: (r, g, b) color used for this panel's header text, divider line and
        border, so several stacked panels for different buses stay visually distinct.
        Defaults to the class's green if not given."""
        self._messages: deque[str] = deque(maxlen=max_messages)
        self._lock = threading.Lock()
        self._active = False
        self._font = None
        self._bus = None
        self._passive = passive
        self._header = f"CAN Traffic  ({channel})"
        self._header_color = accent if accent else self.COLOR_HEADER
        self._divider_color = accent if accent else self.COLOR_DIVIDER
        self._logger = None
        if log_path:
            os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
            self._logger = can.Logger(log_path)

        if passive:
            self._active = True
            return

        try:
            self._bus = can.Bus(**bus_kwargs(channel, serial=serial))
            self._active = True
        except Exception as exc:
            print(f"[CANTrafficDisplay] Could not open {channel}: {exc}")
            return

        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()

    def _format_line(self, msg):
        ts = datetime.datetime.fromtimestamp(msg.timestamp).strftime("%H:%M:%S.%f")[:-3]
        data_str = " ".join(f"{b:02X}" for b in msg.data)
        return f"{ts}  {msg.arbitration_id:03X}  [{msg.dlc}]  {data_str}"

    def feed(self, msg):
        """Passive mode: called by whoever owns the shared bus for each frame on our channel."""
        with self._lock:
            self._messages.append(self._format_line(msg))
        if self._logger:
            self._logger(msg)

    def _recv_loop(self):
        while self._active:
            try:
                msg = self._bus.recv(timeout=1.0)
                if msg is None:
                    continue
                with self._lock:
                    self._messages.append(self._format_line(msg))
                if self._logger:
                    self._logger(msg)
            except can.CanOperationError:
                self._active = False
                break
            except Exception:
                self._active = False
                break

    # ------------------------------------------------------------------
    # Internal helpers
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def stop(self):
        if self._logger:
            self._logger.stop()
        if self._passive:
            return
        self._active = False
        if self._bus:
            self._bus.shutdown()
        if hasattr(self, "_thread"):
            self._thread.join(timeout=2.0)

    def render(self, display: pygame.Surface, slot: int = 0, total_slots: int = 2):
        """slot: 0 = top-right corner, 1 = the box below it, etc. total_slots: how many
        panels are stacked in total — used to split the full screen height evenly
        between them, so the stack always fills the right edge top-to-bottom
        regardless of window size."""
        self._init_font()
        screen_w, screen_h = display.get_size()
        panel_x = screen_w - self.PANEL_WIDTH
        panel_height = (screen_h - self.PANEL_GAP * (total_slots - 1)) // total_slots
        panel_y = slot * (panel_height + self.PANEL_GAP)

        # Semi-transparent background
        bg = pygame.Surface((self.PANEL_WIDTH, panel_height), pygame.SRCALPHA)
        bg.fill((*self.COLOR_BG, 140))
        display.blit(bg, (panel_x, panel_y))

        # Border, to make each stacked box read as a discrete panel
        pygame.draw.rect(
            display, self._header_color, (panel_x, panel_y, self.PANEL_WIDTH, panel_height), 1
        )

        # Header
        status = "" if self._active else "  [unavailable]"
        header_surf = self._font.render(
            self._header + status, True, self._header_color
        )
        display.blit(header_surf, (panel_x + self.PADDING, panel_y + self.PADDING))

        divider_y = panel_y + self.PADDING + self.LINE_HEIGHT + 2
        pygame.draw.line(
            display,
            self._divider_color,
            (panel_x, divider_y),
            (panel_x + self.PANEL_WIDTH, divider_y),
            1,
        )

        if not self._active:
            return

        # Messages – most recent at the top
        with self._lock:
            snapshot = list(self._messages)

        y = divider_y + 4
        panel_bottom = panel_y + panel_height
        visible_lines = max(0, (panel_bottom - y) // self.LINE_HEIGHT)
        for line in reversed(snapshot[-visible_lines:]):
            if y + self.LINE_HEIGHT > panel_bottom:
                break
            surf = self._font.render(line, True, self.COLOR_TEXT)
            display.blit(surf, (panel_x + self.PADDING, y))
            y += self.LINE_HEIGHT
