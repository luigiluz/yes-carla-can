import datetime
import threading
from collections import deque

import can
import pygame


class _CANListener(can.Listener):
    """Passive listener that formats every received CAN frame like candump."""

    def __init__(self, messages: deque, lock: threading.Lock):
        self._messages = messages
        self._lock = lock

    def on_message_received(self, msg: can.Message):
        ts = datetime.datetime.fromtimestamp(msg.timestamp).strftime("%H:%M:%S.%f")[:-3]
        data_str = " ".join(f"{b:02X}" for b in msg.data)
        line = f"{ts}  {msg.arbitration_id:03X}  [{msg.dlc}]  {data_str}"
        with self._lock:
            self._messages.append(line)


class CANTrafficDisplay:
    """
    Renders a live CAN-traffic panel (candump-style) on the right edge of the
    pygame display.  Opens its own read-only bus on *vcan0* so it never
    interferes with the main CAN_Network bus.
    """

    PANEL_WIDTH = 390
    LINE_HEIGHT = 16
    PADDING = 6
    HEADER = "CAN Traffic  (vcan0)"
    COLOR_BG = (0, 0, 0)
    COLOR_HEADER = (0, 230, 100)
    COLOR_TEXT = (160, 255, 160)
    COLOR_DIVIDER = (0, 180, 80)

    def __init__(self, channel: str = "vcan0", max_messages: int = 30):
        self._messages: deque[str] = deque(maxlen=max_messages)
        self._lock = threading.Lock()
        self._active = False
        self._font = None

        try:
            self._bus = can.Bus(interface="socketcan", channel=channel)
            self._notifier = can.Notifier(
                self._bus, [_CANListener(self._messages, self._lock)]
            )
            self._active = True
        except Exception as exc:
            print(f"[CANTrafficDisplay] Could not open {channel}: {exc}")
            self._bus = None
            self._notifier = None

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
            self._font = pygame.font.Font(pygame.font.match_font(name), 13)
        else:
            self._font = pygame.font.Font(pygame.font.get_default_font(), 12)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def stop(self):
        if self._notifier:
            self._notifier.stop()
        if self._bus:
            self._bus.shutdown()

    def render(self, display: pygame.Surface):
        self._init_font()
        screen_w, screen_h = display.get_size()
        panel_x = screen_w - self.PANEL_WIDTH

        # Semi-transparent background
        bg = pygame.Surface((self.PANEL_WIDTH, screen_h), pygame.SRCALPHA)
        bg.fill((*self.COLOR_BG, 140))
        display.blit(bg, (panel_x, 0))

        # Header
        status = "" if self._active else "  [unavailable]"
        header_surf = self._font.render(
            self.HEADER + status, True, self.COLOR_HEADER
        )
        display.blit(header_surf, (panel_x + self.PADDING, self.PADDING))

        divider_y = self.PADDING + self.LINE_HEIGHT + 2
        pygame.draw.line(
            display,
            self.COLOR_DIVIDER,
            (panel_x, divider_y),
            (screen_w, divider_y),
            1,
        )

        if not self._active:
            return

        # Messages – most recent at the top
        with self._lock:
            snapshot = list(self._messages)

        y = divider_y + 4
        for line in reversed(snapshot):
            if y + self.LINE_HEIGHT > screen_h:
                break
            surf = self._font.render(line, True, self.COLOR_TEXT)
            display.blit(surf, (panel_x + self.PADDING, y))
            y += self.LINE_HEIGHT
