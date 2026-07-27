import signal
import sys
import time
import tkinter as tk
from dataclasses import dataclass

import carla

import can_network
from can_network import VCAN_CHANNEL
from can_network.dbc import MESSAGE_SENDERS, SENSOR_MESSAGES

try:
    import pygame
    from pygame.locals import (
        K_COMMA,
        K_DOWN,
        K_ESCAPE,
        K_LEFT,
        K_PERIOD,
        K_RIGHT,
        K_SPACE,
        K_UP,
        KMOD_CTRL,
        KMOD_SHIFT,
        K_a,
        K_d,
        K_i,
        K_l,
        K_m,
        K_o,
        K_q,
        K_s,
        K_w,
        K_x,
        K_z,
    )
except ImportError:
    raise RuntimeError("cannot import pygame, make sure pygame package is installed")


@dataclass(frozen=True)
class ControlBinding:
    key_label: str
    action: str
    category: str
    key_codes: tuple[int, ...]
    behavior: str
    required_modifiers: int = 0
    blocked_modifiers: int = 0


@dataclass(frozen=True)
class KeyCap:
    label: str
    key_codes: tuple[int, ...]
    column: float
    row: float
    width: float = 1.0


@dataclass(frozen=True)
class ControlDisplayState:
    throttle: float
    brake: float
    steer: float
    hand_brake: bool
    reverse: bool
    manual_gear_shift: bool
    gear: int
    active_lights: tuple[str, ...]


@dataclass(frozen=True)
class ControlLayout:
    header: pygame.Rect
    keyboard: pygame.Rect
    legend: pygame.Rect
    state: pygame.Rect


CONTROL_GROUPS = ("Driving", "Transmission", "Lights", "Vehicle", "System")

CONTROL_BINDINGS = (
    ControlBinding("W / Up", "Throttle / accelerate", "Driving", (K_w, K_UP), "HOLD"),
    ControlBinding("S / Down", "Brake", "Driving", (K_s, K_DOWN), "HOLD"),
    ControlBinding("A / Left", "Steer left", "Driving", (K_a, K_LEFT), "HOLD"),
    ControlBinding("D / Right", "Steer right", "Driving", (K_d, K_RIGHT), "HOLD"),
    ControlBinding("Space", "Hand brake", "Driving", (K_SPACE,), "HOLD"),
    ControlBinding("Q", "Toggle reverse gear", "Transmission", (K_q,), "TOGGLE", blocked_modifiers=KMOD_CTRL),
    ControlBinding("M", "Toggle manual shifting", "Transmission", (K_m,), "TOGGLE"),
    ControlBinding(",", "Shift down in manual mode", "Transmission", (K_COMMA,), "PRESS"),
    ControlBinding(".", "Shift up in manual mode", "Transmission", (K_PERIOD,), "PRESS"),
    ControlBinding("L", "Cycle position / low / fog", "Lights", (K_l,), "PRESS", blocked_modifiers=KMOD_CTRL | KMOD_SHIFT),
    ControlBinding("Shift + L", "Toggle high beam", "Lights", (K_l,), "TOGGLE", required_modifiers=KMOD_SHIFT, blocked_modifiers=KMOD_CTRL),
    ControlBinding("Ctrl + L", "Toggle special light", "Lights", (K_l,), "TOGGLE", required_modifiers=KMOD_CTRL),
    ControlBinding("I", "Toggle interior light", "Lights", (K_i,), "TOGGLE"),
    ControlBinding("Z", "Toggle left blinker", "Lights", (K_z,), "TOGGLE"),
    ControlBinding("X", "Toggle right blinker", "Lights", (K_x,), "TOGGLE"),
    ControlBinding("O", "Toggle doors", "Vehicle", (K_o,), "PRESS"),
    ControlBinding("Esc / Ctrl+Q", "Quit controls", "System", (K_ESCAPE,), "PRESS"),
)

KEY_CAPS = (
    KeyCap("ESC", (K_ESCAPE,), 0.0, 0.0),
    KeyCap("Q", (K_q,), 1.0, 1.0),
    KeyCap("W", (K_w,), 2.0, 1.0),
    KeyCap("I", (K_i,), 8.0, 1.0),
    KeyCap("O", (K_o,), 9.0, 1.0),
    KeyCap("A", (K_a,), 1.5, 2.0),
    KeyCap("S", (K_s,), 2.5, 2.0),
    KeyCap("D", (K_d,), 3.5, 2.0),
    KeyCap("L", (K_l,), 8.5, 2.0),
    KeyCap("Z", (K_z,), 2.0, 3.0),
    KeyCap("X", (K_x,), 3.0, 3.0),
    KeyCap("M", (K_m,), 7.0, 3.0),
    KeyCap(",", (K_COMMA,), 8.0, 3.0),
    KeyCap(".", (K_PERIOD,), 9.0, 3.0),
    KeyCap("CTRL", (pygame.K_LCTRL, pygame.K_RCTRL), 0.0, 4.0, 1.3),
    KeyCap("SHIFT", (pygame.K_LSHIFT, pygame.K_RSHIFT), 1.4, 4.0, 1.5),
    KeyCap("SPACE", (K_SPACE,), 3.0, 4.0, 5.0),
    KeyCap("^", (K_UP,), 12.0, 3.0),
    KeyCap("<", (K_LEFT,), 11.0, 4.0),
    KeyCap("v", (K_DOWN,), 12.0, 4.0),
    KeyCap(">", (K_RIGHT,), 13.0, 4.0),
)

LIGHT_FLAGS = (
    ("Position", carla.VehicleLightState.Position),
    ("Low beam", carla.VehicleLightState.LowBeam),
    ("High beam", carla.VehicleLightState.HighBeam),
    ("Brake", carla.VehicleLightState.Brake),
    ("Right blinker", carla.VehicleLightState.RightBlinker),
    ("Left blinker", carla.VehicleLightState.LeftBlinker),
    ("Reverse", carla.VehicleLightState.Reverse),
    ("Fog", carla.VehicleLightState.Fog),
    ("Interior", carla.VehicleLightState.Interior),
    ("Special", carla.VehicleLightState.Special1),
)


class KeyboardSenderControl(object):
    """Class that handles keyboard input and periodic CAN message sending."""

    def __init__(self, can_net, start_in_autopilot=False):
        self._autopilot_enabled = start_in_autopilot
        self._ackermann_enabled = False
        self._ackermann_reverse = 1

        self._can_net = can_net  # store the CAN_Network instance

        self._control = carla.VehicleControl()
        self._ackermann_control = carla.VehicleAckermannControl()
        self._lights = carla.VehicleLightState.NONE

        self._steer_cache = 0.0
        self._last_action = ""
        self._last_action_until = 0.0

        # Build per-message timers from cycle times already loaded by CAN_Network.
        now = time.time()
        # _msg_timers: {msg_name: [interval_seconds, last_sent_timestamp]}
        self._msg_timers = {
            name: [interval, now]
            for name, interval in can_net.cycle_times.items()
            if name in MESSAGE_SENDERS and name not in SENSOR_MESSAGES
        }

    # ------------------------------------------------------------------
    # Periodic sending
    # ------------------------------------------------------------------

    def _send_periodic_messages(self):
        """Fire each message independently according to its DBC cycle time."""
        now = time.time()
        for msg_name, (interval, last_sent) in self._msg_timers.items():
            if now - last_sent >= interval:
                method = getattr(self._can_net, MESSAGE_SENDERS[msg_name], None)
                if method is not None:
                    try:
                        method(self._control)
                    except Exception as e:
                        print(f"[CAN] Failed to send {msg_name}: {e}")
                else:
                    print(
                        f"[CAN] Method {self.MESSAGE_SENDERS[msg_name]} not found on CAN_Network"
                    )
                self._msg_timers[msg_name][1] = now

    def _record_action(self, message):
        self._last_action = message
        self._last_action_until = time.monotonic() + 1.8

    @property
    def recent_action(self):
        if time.monotonic() <= self._last_action_until:
            return self._last_action
        return ""

    def get_display_state(self):
        lights = int(self._lights)
        return ControlDisplayState(
            throttle=float(self._control.throttle),
            brake=float(self._control.brake),
            steer=float(self._control.steer),
            hand_brake=bool(self._control.hand_brake),
            reverse=bool(self._control.reverse),
            manual_gear_shift=bool(self._control.manual_gear_shift),
            gear=int(self._control.gear),
            active_lights=tuple(
                name for name, flag in LIGHT_FLAGS if lights & int(flag)
            ),
        )

    # ------------------------------------------------------------------
    # Key parsing (unchanged logic)
    # ------------------------------------------------------------------

    def _parse_vehicle_keys(self, keys, milliseconds):
        if keys[K_UP] or keys[K_w]:
            if not self._ackermann_enabled:
                self._control.throttle = min(self._control.throttle + 0.1, 1.00)
            else:
                self._ackermann_control.speed += (
                    round(milliseconds * 0.005, 2) * self._ackermann_reverse
                )
        else:
            if not self._ackermann_enabled:
                self._control.throttle = 0.0

        if keys[K_DOWN] or keys[K_s]:
            if not self._ackermann_enabled:
                self._control.brake = min(self._control.brake + 0.2, 1)
            else:
                self._ackermann_control.speed -= (
                    min(
                        abs(self._ackermann_control.speed),
                        round(milliseconds * 0.005, 2),
                    )
                    * self._ackermann_reverse
                )
                self._ackermann_control.speed = (
                    max(0, abs(self._ackermann_control.speed)) * self._ackermann_reverse
                )
        else:
            if not self._ackermann_enabled:
                self._control.brake = 0

        steer_increment = 5e-4 * milliseconds
        if keys[K_LEFT] or keys[K_a]:
            if self._steer_cache > 0:
                self._steer_cache = 0
            else:
                self._steer_cache -= steer_increment
        elif keys[K_RIGHT] or keys[K_d]:
            if self._steer_cache < 0:
                self._steer_cache = 0
            else:
                self._steer_cache += steer_increment
        else:
            self._steer_cache = 0.0
        self._steer_cache = min(0.7, max(-0.7, self._steer_cache))
        if not self._ackermann_enabled:
            self._control.steer = round(self._steer_cache, 1)
            self._control.hand_brake = keys[K_SPACE]
        else:
            self._ackermann_control.steer = round(self._steer_cache, 1)

    def parse_events(self, clock, can_network, events=None):
        current_lights = self._lights
        event_batch = pygame.event.get() if events is None else events
        for event in event_batch:
            if event.type == pygame.QUIT:
                return True
            elif event.type == pygame.KEYUP:
                if self._is_quit_shortcut(event.key):
                    return True
                elif event.key == K_o:
                    try:
                        can_network.send_switch_door_state_msg()
                        self._record_action("Door toggle sent")
                    except:
                        pass
                elif event.key == K_l and pygame.key.get_mods() & KMOD_CTRL:
                    current_lights ^= carla.VehicleLightState.Special1
                    enabled = bool(current_lights & carla.VehicleLightState.Special1)
                    self._record_action(f"Special light {'enabled' if enabled else 'disabled'}")
                elif event.key == K_l and pygame.key.get_mods() & KMOD_SHIFT:
                    current_lights ^= carla.VehicleLightState.HighBeam
                    enabled = bool(current_lights & carla.VehicleLightState.HighBeam)
                    self._record_action(f"High beam {'enabled' if enabled else 'disabled'}")
                elif event.key == K_l:
                    if not self._lights & carla.VehicleLightState.Position:
                        current_lights |= carla.VehicleLightState.Position
                    else:
                        current_lights |= carla.VehicleLightState.LowBeam
                    if self._lights & carla.VehicleLightState.LowBeam:
                        current_lights |= carla.VehicleLightState.Fog
                    if self._lights & carla.VehicleLightState.Fog:
                        current_lights ^= carla.VehicleLightState.Position
                        current_lights ^= carla.VehicleLightState.LowBeam
                        current_lights ^= carla.VehicleLightState.Fog
                    self._record_action("Exterior light mode changed")
                elif event.key == K_i:
                    current_lights ^= carla.VehicleLightState.Interior
                    enabled = bool(current_lights & carla.VehicleLightState.Interior)
                    self._record_action(f"Interior light {'enabled' if enabled else 'disabled'}")
                elif event.key == K_z:
                    current_lights ^= carla.VehicleLightState.LeftBlinker
                    enabled = bool(current_lights & carla.VehicleLightState.LeftBlinker)
                    self._record_action(f"Left blinker {'enabled' if enabled else 'disabled'}")
                elif event.key == K_x:
                    current_lights ^= carla.VehicleLightState.RightBlinker
                    enabled = bool(current_lights & carla.VehicleLightState.RightBlinker)
                    self._record_action(f"Right blinker {'enabled' if enabled else 'disabled'}")
                elif event.key == K_q:
                    if not self._ackermann_enabled:
                        self._control.gear = 1 if self._control.reverse else -1
                        enabled = self._control.gear < 0
                        self._record_action(f"Reverse {'enabled' if enabled else 'disabled'}")
                    else:
                        self._ackermann_reverse *= -1
                        self._ackermann_control = carla.VehicleAckermannControl()
                elif event.key == K_m:
                    self._control.manual_gear_shift = (
                        not self._control.manual_gear_shift
                    )
                    enabled = self._control.manual_gear_shift
                    self._record_action(f"Manual shifting {'enabled' if enabled else 'disabled'}")
                elif self._control.manual_gear_shift and event.key == K_COMMA:
                    self._control.gear = max(-1, self._control.gear - 1)
                    self._record_action(f"Shifted down to gear {self._control.gear}")
                elif self._control.manual_gear_shift and event.key == K_PERIOD:
                    self._control.gear = self._control.gear + 1
                    self._record_action(f"Shifted up to gear {self._control.gear}")

        self._parse_vehicle_keys(pygame.key.get_pressed(), clock.get_time())
        self._control.reverse = self._control.gear < 0

        # Automatic light flags
        if self._control.brake:
            current_lights |= carla.VehicleLightState.Brake
        else:
            current_lights &= ~carla.VehicleLightState.Brake
        if self._control.reverse:
            current_lights |= carla.VehicleLightState.Reverse
        else:
            current_lights &= ~carla.VehicleLightState.Reverse

        # Event-driven: lights changed → send immediately
        if self._lights != current_lights:
            can_network.send_current_lights_msg(current_lights)
            self._lights = current_lights

        # Periodic: send each message according to its DBC cycle time
        self._send_periodic_messages()

    @staticmethod
    def _is_quit_shortcut(key):
        return (key == K_ESCAPE) or (key == K_q and pygame.key.get_mods() & KMOD_CTRL)


MIN_WINDOW_WIDTH = 960
MIN_WINDOW_HEIGHT = 600

COLORS = {
    "background": (16, 19, 23),
    "surface": (24, 29, 35),
    "surface_active": (34, 50, 45),
    "border": (65, 73, 82),
    "text": (235, 239, 243),
    "muted": (159, 170, 181),
    "key": (205, 211, 217),
    "key_text": (20, 24, 28),
    "active": (75, 210, 145),
    "cyan": (77, 181, 219),
    "amber": (235, 174, 73),
}

_FONT_CACHE = {}


def calculate_control_layout(width, height):
    padding = max(12, min(22, int(min(width, height) * 0.022)))
    gap = padding
    header_height = max(62, int(height * 0.10))
    state_height = max(126, int(height * 0.20))
    content_top = padding + header_height + gap
    state_top = height - padding - state_height
    content_height = state_top - gap - content_top
    content_width = width - 2 * padding
    keyboard_width = int((content_width - gap) * 0.58)

    return ControlLayout(
        header=pygame.Rect(padding, padding, content_width, header_height),
        keyboard=pygame.Rect(padding, content_top, keyboard_width, content_height),
        legend=pygame.Rect(
            padding + keyboard_width + gap,
            content_top,
            content_width - keyboard_width - gap,
            content_height,
        ),
        state=pygame.Rect(padding, state_top, content_width, state_height),
    )


def _get_font(size, bold=False):
    key = (max(10, int(size)), bold)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = pygame.font.SysFont("DejaVu Sans", key[0], bold=bold)
    return _FONT_CACHE[key]


def _draw_fitted_text(surface, text, rect, color, size, bold=False, align="left"):
    rect = pygame.Rect(rect)
    current_size = max(10, int(size))
    font = _get_font(current_size, bold)
    rendered = font.render(str(text), True, color)
    while current_size > 10 and rendered.get_width() > rect.width:
        current_size -= 1
        font = _get_font(current_size, bold)
        rendered = font.render(str(text), True, color)

    if align == "center":
        target = rendered.get_rect(center=rect.center)
    elif align == "right":
        target = rendered.get_rect(midright=(rect.right, rect.centery))
    else:
        target = rendered.get_rect(midleft=(rect.left, rect.centery))
    previous_clip = surface.get_clip()
    surface.set_clip(rect)
    surface.blit(rendered, target)
    surface.set_clip(previous_clip)


def _binding_is_active(binding, pressed, modifiers):
    if not any(pressed[key_code] for key_code in binding.key_codes):
        return False
    if binding.required_modifiers:
        if not modifiers & binding.required_modifiers:
            return False
    if binding.blocked_modifiers and modifiers & binding.blocked_modifiers:
        return False
    return True


def _draw_header(surface, rect, controller, pressed, modifiers):
    pygame.draw.rect(surface, COLORS["surface"], rect, border_radius=6)
    title_rect = pygame.Rect(rect.x + 18, rect.y, int(rect.width * 0.32), rect.height)
    _draw_fitted_text(
        surface,
        "Vehicle Controls",
        title_rect,
        COLORS["text"],
        rect.height * 0.34,
        bold=True,
    )

    active_actions = [
        binding.action
        for binding in CONTROL_BINDINGS
        if binding.behavior == "HOLD"
        and _binding_is_active(binding, pressed, modifiers)
    ]
    if active_actions:
        status = " + ".join(active_actions)
        status_color = COLORS["active"]
    elif controller is None:
        status = "Connecting to CAN interface"
        status_color = COLORS["muted"]
    elif controller.recent_action:
        status = controller.recent_action
        status_color = COLORS["active"]
    else:
        status = "Controls ready"
        status_color = COLORS["muted"]

    status_rect = pygame.Rect(
        title_rect.right + 18,
        rect.y,
        rect.right - title_rect.right - 36,
        rect.height,
    )
    _draw_fitted_text(
        surface,
        status,
        status_rect,
        status_color,
        rect.height * 0.27,
        bold=True,
        align="right",
    )


def _draw_keyboard(surface, rect, pressed):
    title_height = max(24, int(rect.height * 0.08))
    _draw_fitted_text(
        surface,
        "Keyboard",
        pygame.Rect(rect.x, rect.y, rect.width, title_height),
        COLORS["text"],
        title_height * 0.68,
        bold=True,
    )
    pygame.draw.line(
        surface,
        COLORS["border"],
        (rect.x, rect.y + title_height),
        (rect.right, rect.y + title_height),
    )

    grid = pygame.Rect(rect.x, rect.y + title_height + 10, rect.width, rect.height - title_height - 10)
    columns = 14
    rows = 5
    gap = max(4, int(rect.width * 0.008))
    key_width = (grid.width - gap * (columns - 1)) / columns
    key_height = min(
        key_width * 0.88,
        (grid.height - gap * (rows - 1)) / rows,
    )
    grid_height = rows * key_height + gap * (rows - 1)
    start_y = grid.y + max(0, (grid.height - grid_height) / 2)

    for key_cap in KEY_CAPS:
        x = grid.x + key_cap.column * (key_width + gap)
        y = start_y + key_cap.row * (key_height + gap)
        width = key_cap.width * key_width + (key_cap.width - 1) * gap
        key_rect = pygame.Rect(round(x), round(y), round(width), round(key_height))
        active = any(pressed[key_code] for key_code in key_cap.key_codes)
        fill = COLORS["active"] if active else COLORS["key"]
        pygame.draw.rect(surface, fill, key_rect, border_radius=6)
        pygame.draw.rect(surface, COLORS["border"], key_rect, width=1, border_radius=6)
        _draw_fitted_text(
            surface,
            key_cap.label,
            key_rect.inflate(-8, -4),
            COLORS["key_text"],
            key_height * 0.40,
            bold=True,
            align="center",
        )


def _draw_legend(surface, rect, pressed, modifiers):
    title_height = max(24, int(rect.height * 0.08))
    _draw_fitted_text(
        surface,
        "Bindings",
        pygame.Rect(rect.x, rect.y, rect.width, title_height),
        COLORS["text"],
        title_height * 0.68,
        bold=True,
    )
    pygame.draw.line(
        surface,
        COLORS["border"],
        (rect.x, rect.y + title_height),
        (rect.right, rect.y + title_height),
    )

    groups = [
        (group, [binding for binding in CONTROL_BINDINGS if binding.category == group])
        for group in CONTROL_GROUPS
    ]
    content_top = rect.y + title_height + 6
    available_height = rect.bottom - content_top
    group_title_height = max(13, min(18, int(available_height * 0.04)))
    group_gap = 3
    row_count = len(CONTROL_BINDINGS)
    row_height = max(
        14,
        int(
            (
                available_height
                - len(groups) * group_title_height
                - (len(groups) - 1) * group_gap
            )
            / row_count
        ),
    )
    key_width = max(86, int(rect.width * 0.29))
    behavior_width = max(42, int(rect.width * 0.12))
    y = content_top

    for group, bindings in groups:
        _draw_fitted_text(
            surface,
            group.upper(),
            pygame.Rect(rect.x, y, rect.width, group_title_height),
            COLORS["cyan"],
            group_title_height * 0.72,
            bold=True,
        )
        y += group_title_height

        for binding in bindings:
            row_rect = pygame.Rect(rect.x, y, rect.width, row_height)
            active = _binding_is_active(binding, pressed, modifiers)
            if active:
                pygame.draw.rect(surface, COLORS["surface_active"], row_rect)

            key_rect = pygame.Rect(row_rect.x, row_rect.y + 1, key_width - 8, row_height - 2)
            pygame.draw.rect(
                surface,
                COLORS["active"] if active else COLORS["surface"],
                key_rect,
                border_radius=4,
            )
            _draw_fitted_text(
                surface,
                binding.key_label,
                key_rect.inflate(-6, 0),
                COLORS["key_text"] if active else COLORS["text"],
                row_height * 0.56,
                bold=True,
                align="center",
            )

            action_rect = pygame.Rect(
                row_rect.x + key_width,
                row_rect.y,
                row_rect.width - key_width - behavior_width - 6,
                row_height,
            )
            _draw_fitted_text(
                surface,
                binding.action,
                action_rect,
                COLORS["text"],
                row_height * 0.58,
            )
            _draw_fitted_text(
                surface,
                binding.behavior,
                pygame.Rect(row_rect.right - behavior_width, row_rect.y, behavior_width, row_height),
                COLORS["active"] if active else COLORS["muted"],
                row_height * 0.48,
                bold=True,
                align="right",
            )
            y += row_height
        y += group_gap


def _draw_meter(surface, rect, label, value, color, centered=False):
    value = max(-1.0 if centered else 0.0, min(1.0, value))
    label_rect = pygame.Rect(rect.x, rect.y, rect.width, int(rect.height * 0.42))
    _draw_fitted_text(
        surface,
        f"{label}  {value:+.0%}" if centered else f"{label}  {value:.0%}",
        label_rect,
        COLORS["text"],
        label_rect.height * 0.58,
        bold=True,
    )
    bar = pygame.Rect(rect.x, label_rect.bottom + 3, rect.width, max(8, int(rect.height * 0.26)))
    pygame.draw.rect(surface, COLORS["surface"], bar, border_radius=3)
    pygame.draw.rect(surface, COLORS["border"], bar, width=1, border_radius=3)
    if centered:
        center = bar.centerx
        fill_width = int(abs(value) * (bar.width / 2))
        fill = pygame.Rect(center if value >= 0 else center - fill_width, bar.y, fill_width, bar.height)
        pygame.draw.line(surface, COLORS["muted"], (center, bar.y), (center, bar.bottom))
    else:
        fill = pygame.Rect(bar.x, bar.y, int(value * bar.width), bar.height)
    if fill.width > 0:
        pygame.draw.rect(surface, color, fill, border_radius=3)


def _draw_state(surface, rect, state):
    pygame.draw.rect(surface, COLORS["surface"], rect, border_radius=6)
    padding = max(12, int(rect.height * 0.11))
    title_height = max(20, int(rect.height * 0.20))
    _draw_fitted_text(
        surface,
        "Command State",
        pygame.Rect(rect.x + padding, rect.y + 2, rect.width - 2 * padding, title_height),
        COLORS["text"],
        title_height * 0.62,
        bold=True,
    )

    meter_region_width = int(rect.width * 0.55)
    meter_top = rect.y + title_height + 4
    meter_height = rect.bottom - padding - meter_top
    meter_gap = max(10, int(rect.width * 0.012))
    meter_width = int((meter_region_width - 2 * padding - 2 * meter_gap) / 3)
    meters = (
        ("Throttle", state.throttle, COLORS["active"], False),
        ("Brake", state.brake, COLORS["amber"], False),
        ("Steer", state.steer, COLORS["cyan"], True),
    )
    for index, (label, value, color, centered) in enumerate(meters):
        meter_rect = pygame.Rect(
            rect.x + padding + index * (meter_width + meter_gap),
            meter_top,
            meter_width,
            meter_height,
        )
        _draw_meter(surface, meter_rect, label, value, color, centered)

    details_x = rect.x + meter_region_width + padding
    details_width = rect.right - padding - details_x
    detail_height = max(20, int((rect.height - 2 * padding) / 3))
    gear = "R" if state.reverse else ("N" if state.gear == 0 else str(state.gear))
    if len(state.active_lights) > 3:
        lights = ", ".join(state.active_lights[:3]) + f", +{len(state.active_lights) - 3}"
    else:
        lights = ", ".join(state.active_lights) if state.active_lights else "Off"
    detail_lines = (
        f"Gear  {gear}    Manual  {'ON' if state.manual_gear_shift else 'OFF'}",
        f"Reverse  {'ON' if state.reverse else 'OFF'}    Hand brake  {'ON' if state.hand_brake else 'OFF'}",
        f"Lights  {lights}",
    )
    for index, line in enumerate(detail_lines):
        _draw_fitted_text(
            surface,
            line,
            pygame.Rect(details_x, rect.y + padding + index * detail_height, details_width, detail_height),
            COLORS["active"] if index == 2 and state.active_lights else COLORS["text"],
            detail_height * 0.52,
            bold=index < 2,
        )


def draw_control_interface(surface, controller, pressed, modifiers):
    surface.fill(COLORS["background"])
    layout = calculate_control_layout(*surface.get_size())
    state = (
        controller.get_display_state()
        if controller is not None
        else ControlDisplayState(0.0, 0.0, 0.0, False, False, False, 0, ())
    )
    _draw_header(surface, layout.header, controller, pressed, modifiers)
    _draw_keyboard(surface, layout.keyboard, pressed)
    _draw_legend(surface, layout.legend, pressed, modifiers)
    _draw_state(surface, layout.state, state)


def keyboard_parser_loop(dbc_path="data/carla.dbc", vcan_channel=None):
    print("Starting keyboard parser loop")
    pygame.init()
    pygame.font.init()

    root = tk.Tk()
    desktop_width = root.winfo_screenwidth()
    desktop_height = root.winfo_screenheight()
    root.destroy()
    print(f"width: {desktop_width}, height: {desktop_height}")

    width = min(max(MIN_WINDOW_WIDTH, int(desktop_width * 0.72)), desktop_width - 40)
    height = min(max(MIN_WINDOW_HEIGHT, int(desktop_height * 0.68)), desktop_height - 80)
    screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
    pygame.display.set_caption("Yes, CARLA CAN - Vehicle Controls")

    pressed = pygame.key.get_pressed()
    draw_control_interface(screen, None, pressed, pygame.key.get_mods())
    pygame.display.flip()

    can_net = None
    try:
        can_net = can_network.CAN_Network(dbc_path=dbc_path, channel=vcan_channel)
        controller = KeyboardSenderControl(can_net)
        scheduled = [
            f"{name}({int(interval[0] * 1000)}ms)"
            for name, interval in sorted(controller._msg_timers.items())
        ]
        print(f"[CAN] DBC loaded: {dbc_path}")
        print(f"[CAN] Periodic messages scheduled: {' '.join(scheduled)}")
        clock = pygame.time.Clock()
        running = True

        while running:
            clock.tick_busy_loop(60)
            events = pygame.event.get()
            for event in events:
                if event.type == pygame.VIDEORESIZE:
                    resized = (
                        max(MIN_WINDOW_WIDTH, event.w),
                        max(MIN_WINDOW_HEIGHT, event.h),
                    )
                    screen = pygame.display.set_mode(resized, pygame.RESIZABLE)

            if controller.parse_events(clock, can_net, events):
                running = False
                continue

            pressed = pygame.key.get_pressed()
            draw_control_interface(
                screen,
                controller,
                pressed,
                pygame.key.get_mods(),
            )
            pygame.display.flip()
    finally:
        if can_net is not None:
            can_net.bus.shutdown()
        pygame.quit()


def print_key_bindings():
    key_width = max(len(binding.key_label) for binding in CONTROL_BINDINGS) + 2
    print()
    print("  CAN Sender - Key Bindings")
    print("  " + "-" * (key_width + 46))
    for group in CONTROL_GROUPS:
        print(f"  {group.upper()}")
        for binding in CONTROL_BINDINGS:
            if binding.category == group:
                print(
                    f"  {binding.key_label:<{key_width}} "
                    f"{binding.action:<32} [{binding.behavior.lower()}]"
                )
    print("  " + "-" * (key_width + 46))
    print()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Vehicle Controls Module")
    parser.add_argument(
        "--dbc",
        default="data/carla.dbc",
        help="Path to the DBC file (default: data/carla.dbc)",
    )
    parser.add_argument(
        "--vcan",
        default=VCAN_CHANNEL,
        help=f"Virtual CAN interface name (default: {VCAN_CHANNEL})",
    )
    args = parser.parse_args()

    # Ensure SIGTERM (e.g. from environment_down.sh) also exits cleanly
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    print("Sending commands through CAN bus")
    print_key_bindings()
    try:
        keyboard_parser_loop(dbc_path=args.dbc, vcan_channel=args.vcan)
    except (KeyboardInterrupt, SystemExit):
        print("\nCancelled by user. Bye!")
        pygame.quit()
        sys.exit(0)


if __name__ == "__main__":
    main()
