import shlex
import threading
import time
from collections import deque

import can
import pygame

from can_network.bus_config import CAN_INTERFACE, VCAN_CHANNEL, bus_kwargs
from can_network import VCAN_ATTACKER_CHANNEL
from cyberattacks_module import (
    available_features,
    build_parser,
    denial_of_service_func,
    fuzzy_attack_func,
    spoofing_attacks_func,
)


class AttackTerminalPanel:
    """A terminal-style overlay inside the CARLA client window for launching CAN attacks,
    so the attacker no longer needs its own device/shell. Press K to open it (see
    gui/keyboard_control.py); while open it captures the keyboard and you type the same
    arguments the standalone cyberattacks_module.py CLI takes, e.g.:

        --feature hand_brake --period 0.001
        --feature fuzzy
        --feature denial_of_service --channel HSCAN

    Built-ins: 'stop' ends the running attack, 'list'/'help' shows the features, 'clear'
    wipes the log, Esc closes the panel. One attack runs at a time.

    How frames reach the bus depends on the backend:
      * socketcan/vcan: we open our OWN bus on the typed --channel (default vcan1), exactly
        like the CLI, so can-gw still tags the frames 'R' for labeled datasets.
      * neovi (physical): the device is exclusive and the CARLA client already holds it open,
        so we must NOT open a second handle. We inject through the client's already-open
        SharedPhysicalBus (a ThreadSafeBus, safe for concurrent send()), stamping each frame
        with the target channel's netid and send timeout 0.
    """

    ACCENT = (255, 96, 64)
    TEXT = (235, 235, 235)
    RUN = (255, 82, 87)
    DIM = (130, 130, 130)
    MAX_WIDTH = 760
    MAX_HEIGHT = 340
    LINE_HEIGHT = 20
    PADDING = 8
    MARGIN = 12

    def __init__(self, physical_bus=None, powertrain_channel=None, comfort_channel=None,
                 max_lines: int = 200):
        """physical_bus: the client's shared ThreadSafeBus when running on the neovi backend,
        else None. powertrain_channel/comfort_channel: the client's channel names, used to
        default/resolve the attacker channel in physical mode."""
        self.visible = False
        self.focused = False
        self._physical_bus = physical_bus
        self._powertrain_channel = powertrain_channel
        self._comfort_channel = comfort_channel

        self._input = ""
        self._history = []
        self._hist_idx = 0
        self._output = deque(maxlen=max_lines)
        self._lock = threading.Lock()
        self._font = None

        self._thread = None
        self._stop_event = None
        self._status = None
        self._current = None

        self._own_bus = None
        self._own_channel = None

        self._print("type 'list' for features, 'stop' to end, Esc to close")

    # ------------------------------------------------------------------
    # Input handling (called from the pygame main thread while focused)
    # ------------------------------------------------------------------

    def toggle(self):
        self.visible = not self.visible
        self.focused = self.visible
        return self.visible

    def handle_key(self, event):
        key = event.key
        if key == pygame.K_RETURN:
            line = self._input
            self._input = ""
            if line.strip():
                self._history.append(line)
            self._hist_idx = len(self._history)
            self._print(f"attack> {line}")
            self.run(line)
        elif key == pygame.K_BACKSPACE:
            self._input = self._input[:-1]
        elif key == pygame.K_ESCAPE:
            self.visible = False
            self.focused = False
        elif key == pygame.K_UP:
            if self._history:
                self._hist_idx = max(0, self._hist_idx - 1)
                self._input = self._history[self._hist_idx]
        elif key == pygame.K_DOWN:
            if self._history:
                self._hist_idx = min(len(self._history), self._hist_idx + 1)
                self._input = self._history[self._hist_idx] if self._hist_idx < len(self._history) else ""
        else:
            ch = event.unicode
            if ch and ch.isprintable():
                self._input += ch

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    def run(self, line):
        line = line.strip()
        if not line:
            return
        cmd = line.lower()
        if cmd == "stop":
            self.stop_attack()
            return
        if cmd in ("help", "list"):
            self._print("features: " + ", ".join(available_features()))
            self._print("usage: --feature <name> [--period S] [--channel CH]")
            return
        if cmd == "clear":
            with self._lock:
                self._output.clear()
            return

        if self._thread is not None and self._thread.is_alive():
            self._print("an attack is already running - type 'stop' first")
            return

        try:
            args = build_parser(exit_on_error=False).parse_args(shlex.split(line))
        except Exception as exc:
            self._print(f"error: {exc}")
            return
        if not args.feature:
            self._print("no --feature given (try 'list')")
            return

        try:
            bus, send_channel, send_timeout = self._resolve(args)
        except Exception as exc:
            self._print(f"error: {exc}")
            return

        self._stop_event = threading.Event()
        kw = dict(stop_event=self._stop_event, send_channel=send_channel,
                  send_timeout=send_timeout, on_status=self._on_status)
        if args.feature == "fuzzy":
            pos = (bus,)
            fn = fuzzy_attack_func
        elif args.feature == "denial_of_service":
            pos = (bus, args.period)
            fn = denial_of_service_func
        else:
            pos = (bus, args.feature, args.period)
            fn = spoofing_attacks_func

        self._current = args.feature
        self._thread = threading.Thread(target=self._run_attack, args=(fn, pos, kw), daemon=True)
        self._thread.start()
        self._print(f"started {args.feature}")

    def _resolve(self, args):
        """Return (bus, send_channel, send_timeout) for the active backend, or raise."""
        if CAN_INTERFACE == "neovi":
            if self._physical_bus is None:
                raise RuntimeError("client is not on the neovi backend - no shared bus to inject on")
            # In physical mode the attacker shares the client's device; a vcan default means
            # the user didn't pick a channel, so aim at the powertrain segment by default.
            channel = args.channel
            if channel in (VCAN_ATTACKER_CHANNEL, VCAN_CHANNEL) and self._powertrain_channel:
                channel = self._powertrain_channel
            from can.interfaces.ics_neovi.neovi_bus import NeoViBus
            return self._physical_bus, NeoViBus.channel_to_netid(channel), 0

        # socketcan/vcan: open (and reuse) our own bus on the typed channel.
        if self._own_bus is None or self._own_channel != args.channel:
            if self._own_bus is not None:
                try:
                    self._own_bus.shutdown()
                except Exception:
                    pass
            self._own_bus = can.Bus(**bus_kwargs(args.channel, serial=args.can_serial))
            self._own_channel = args.channel
        return self._own_bus, None, None

    def _run_attack(self, fn, pos, kw):
        try:
            fn(*pos, **kw)
        except Exception as exc:
            self._print(f"attack error: {exc}")
        finally:
            with self._lock:
                self._status = None

    def _on_status(self, attack_type, feature, sent, rate, last_msg):
        with self._lock:
            self._status = {
                "attack": attack_type,
                "sent": sent,
                "rate": rate,
                "id": last_msg.arbitration_id,
            }

    def stop_attack(self):
        running = self._thread is not None and self._thread.is_alive()
        if self._stop_event is not None:
            self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
        was = self._current
        with self._lock:
            self._status = None
        self._current = None
        self._print(f"stopped {was}" if running and was else "nothing to stop")

    def stop(self):
        """Client shutdown: end any attack and close our own bus."""
        self.stop_attack()
        if self._own_bus is not None:
            try:
                self._own_bus.shutdown()
            except Exception:
                pass
            self._own_bus = None

    def _print(self, text):
        with self._lock:
            self._output.append(text)

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

    def render(self, display: pygame.Surface):
        if not self.visible:
            return
        self._init_font()
        screen_w, screen_h = display.get_size()
        w = min(self.MAX_WIDTH, screen_w - 2 * self.MARGIN)
        h = min(self.MAX_HEIGHT, screen_h - 2 * self.MARGIN)
        x = self.MARGIN
        y = screen_h - h - self.MARGIN
        pad = self.PADDING
        line_h = self.LINE_HEIGHT

        bg = pygame.Surface((w, h), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 185))
        display.blit(bg, (x, y))
        pygame.draw.rect(display, self.ACCENT, (x, y, w, h), 1)

        with self._lock:
            status = dict(self._status) if self._status else None
            output = list(self._output)

        display.blit(self._font.render("ATTACK TERMINAL", True, self.ACCENT), (x + pad, y + pad))
        if status:
            st = "RUNNING %s  sent=%d  %.1f msg/s  last=0x%03X" % (
                status["attack"], status["sent"], status["rate"], status["id"])
            st_color = self.RUN
        else:
            st = "idle"
            st_color = self.DIM
        st_surf = self._font.render(st, True, st_color)
        display.blit(st_surf, (x + w - st_surf.get_width() - pad, y + pad))

        divider_y = y + pad + line_h
        pygame.draw.line(display, self.ACCENT, (x, divider_y), (x + w, divider_y), 1)

        cursor = "_" if int(time.time() * 2) % 2 == 0 else " "
        prompt_y = y + h - line_h - pad
        pygame.draw.line(display, self.ACCENT, (x, prompt_y - 4), (x + w, prompt_y - 4), 1)
        prompt = self._font.render(f"attack> {self._input}{cursor}", True, self.TEXT)
        display.blit(prompt, (x + pad, prompt_y))

        top = divider_y + 6
        max_chars = max(10, (w - 2 * pad) // 9)
        avail = max(0, (prompt_y - 8 - top) // line_h)
        for i, text in enumerate(output[-avail:]):
            surf = self._font.render(text[:max_chars], True, self.TEXT)
            display.blit(surf, (x + pad, top + i * line_h))
