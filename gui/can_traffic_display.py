import datetime
import threading
from collections import deque

import can
import pygame

from can_network.bus_config import VCAN_CHANNEL, bus_kwargs


class CANTrafficDisplay:
    """
    Renders a live CAN-traffic panel (candump-style) on the right edge of the
    pygame display.  Opens its own read-only bus on *vcan0* so it never
    interferes with the main CAN_Network bus.
    """

    PANEL_WIDTH = 480
    LINE_HEIGHT = 22
    PADDING = 8
    COLOR_BG = (0, 0, 0)
    COLOR_HEADER = (0, 230, 100)
    COLOR_TEXT = (160, 255, 160)
    COLOR_DIVIDER = (0, 180, 80)

    def __init__(self, channel: str = VCAN_CHANNEL, serial: str = None, max_messages: int = 30,
                 passive: bool = False):
        """passive=True: don't open a bus/thread of our own — the caller feeds frames via
        feed(), e.g. a SharedPhysicalBus that already owns the one allowed handle to this
        physical device. Used on the neovi backend, where opening yet another handle to
        the same device would fail."""
        self._messages: deque[str] = deque(maxlen=max_messages)
        self._lock = threading.Lock()
        self._active = False
        self._font = None
        self._bus = None
        self._passive = passive
        self._header = f"CAN Traffic  ({channel})"

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

    def _recv_loop(self):
        while self._active:
            try:
                msg = self._bus.recv(timeout=1.0)
                if msg is None:
                    continue
                with self._lock:
                    self._messages.append(self._format_line(msg))
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
        if self._passive:
            return
        self._active = False
        if self._bus:
            self._bus.shutdown()
        if hasattr(self, "_thread"):
            self._thread.join(timeout=2.0)

    def render(self, display: pygame.Surface, slot: int = 0):
        """slot: 0 = rightmost panel, 1 = the one to its left, etc. — lets several
        CANTrafficDisplay instances (one per bus/channel) be drawn side by side."""
        self._init_font()
        screen_w, screen_h = display.get_size()
        panel_x = screen_w - self.PANEL_WIDTH * (slot + 1)

        # Semi-transparent background
        bg = pygame.Surface((self.PANEL_WIDTH, screen_h), pygame.SRCALPHA)
        bg.fill((*self.COLOR_BG, 140))
        display.blit(bg, (panel_x, 0))

        # Header
        status = "" if self._active else "  [unavailable]"
        header_surf = self._font.render(
            self._header + status, True, self.COLOR_HEADER
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
