import time
import tkinter as tk

import cantools
import carla

import can_network

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

DBC_PATH = "data/carla.dbc"


def load_cycle_times(dbc_path):
    """
    Parse the DBC and return a dict of {message_name: cycle_time_seconds}.
    Messages with GenMsgCycleTime == 0 are considered event-driven (not periodic).
    """
    db = cantools.database.load_file(dbc_path)
    cycle_times = {}
    for msg in db.messages:
        cycle_ms = msg.cycle_time  # cantools reads GenMsgCycleTime automatically
        if cycle_ms and cycle_ms > 0:
            cycle_times[msg.name] = cycle_ms / 1000.0  # convert ms → seconds
    return cycle_times


class KeyboardSenderControl(object):
    """Class that handles keyboard input and periodic CAN message sending."""

    # Maps DBC message name → CAN_Network method name to call
    MESSAGE_SENDERS = {
        "THROTTLE": "send_throttle_msg",
        "BRAKE": "send_brake_msg",
        "STEER": "send_steer_msg",
        "REVERSE": "send_reverse_msg",
        "HAND_BRAKE": "send_hand_brake_msg",
        "AUTOPILOT": "send_autopilot_msg",
        "MANUAL_TRANSMISSION": "send_manual_transmission_msg",
        "GEAR": "send_gear_msg",
    }

    def __init__(self, can_net, dbc_path=DBC_PATH, start_in_autopilot=False):
        self._autopilot_enabled = start_in_autopilot
        self._ackermann_enabled = False
        self._ackermann_reverse = 1

        self._can_net = can_net  # store the CAN_Network instance

        self._control = carla.VehicleControl()
        self._ackermann_control = carla.VehicleAckermannControl()
        self._lights = carla.VehicleLightState.NONE

        self._steer_cache = 0.0

        # Load per-message cycle times from DBC and initialise last-sent timestamps.
        cycle_times = load_cycle_times(dbc_path)
        now = time.time()
        # _msg_timers: {msg_name: [interval_seconds, last_sent_timestamp]}
        self._msg_timers = {
            name: [interval, now]
            for name, interval in cycle_times.items()
            if name in self.MESSAGE_SENDERS
        }

    # ------------------------------------------------------------------
    # Periodic sending
    # ------------------------------------------------------------------

    def _send_periodic_messages(self):
        """Fire each message independently according to its DBC cycle time."""
        now = time.time()
        for msg_name, (interval, last_sent) in self._msg_timers.items():
            if now - last_sent >= interval:
                method = getattr(self._can_net, self.MESSAGE_SENDERS[msg_name], None)
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

    def parse_events(self, clock, can_network):
        current_lights = self._lights
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return True
            elif event.type == pygame.KEYUP:
                if self._is_quit_shortcut(event.key):
                    return True
                elif event.key == K_o:
                    try:
                        can_network.send_switch_door_state_msg()
                    except:
                        pass
                elif event.key == K_l and pygame.key.get_mods() & KMOD_CTRL:
                    current_lights ^= carla.VehicleLightState.Special1
                elif event.key == K_l and pygame.key.get_mods() & KMOD_SHIFT:
                    current_lights ^= carla.VehicleLightState.HighBeam
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
                elif event.key == K_i:
                    current_lights ^= carla.VehicleLightState.Interior
                elif event.key == K_z:
                    current_lights ^= carla.VehicleLightState.LeftBlinker
                elif event.key == K_x:
                    current_lights ^= carla.VehicleLightState.RightBlinker
                if event.key == K_q:
                    if not self._ackermann_enabled:
                        self._control.gear = 1 if self._control.reverse else -1
                    else:
                        self._ackermann_reverse *= -1
                        self._ackermann_control = carla.VehicleAckermannControl()
                elif event.key == K_m:
                    self._control.manual_gear_shift = (
                        not self._control.manual_gear_shift
                    )
                elif self._control.manual_gear_shift and event.key == K_COMMA:
                    self._control.gear = max(-1, self._control.gear - 1)
                elif self._control.manual_gear_shift and event.key == K_PERIOD:
                    self._control.gear = self._control.gear + 1

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


def keyboard_parser_loop():
    print("Starting keyboard parser loop")
    pygame.init()
    pygame.font.init()

    root = tk.Tk()
    width = root.winfo_screenwidth()
    height = root.winfo_screenheight()
    root.destroy()
    print(f"width: {width}, height: {height}")
    WIDTH = int(width * 0.45)
    HEIGHT = int(height * 0.33)
    screen = pygame.display.set_mode((WIDTH, HEIGHT))

    # Interface related
    # Colors
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)
    GRAY = (200, 200, 200)
    GREEN = (100, 255, 100)
    DARK_GRAY = (50, 50, 50)

    key_definitions = [
        (pygame.K_q, "Q", "Reverse"),
        (pygame.K_w, "W", "Move Forward"),
        (pygame.K_i, "I", "Interior Light"),
        (pygame.K_o, "O", "Doors"),
        (pygame.K_a, "A", "Move Left"),
        (pygame.K_s, "S", "Brake"),
        (pygame.K_d, "D", "Move Right"),
        (pygame.K_l, "L", "Light type"),
        (pygame.K_z, "Z", "Left Blinker"),
        (pygame.K_x, "X", "Right Blinker"),
        (pygame.K_m, "M", "Manual"),
        (pygame.K_COMMA, ",", "Gear Up"),
        (pygame.K_PERIOD, ".", "Gear Down"),
        (pygame.K_LSHIFT, "SHIFT", ""),
        (pygame.K_SPACE, "SPACE", "Hand Brake"),
        (pygame.K_ESCAPE, "ESC", "Exit"),
        (pygame.K_UP, "^", "Move Forward"),
        (pygame.K_DOWN, "v", "Brake"),
        (pygame.K_LEFT, "<", "Steer Left"),
        (pygame.K_RIGHT, ">", "Steer Right"),
    ]

    key_positions = {
        "Q": (1, 1),
        "W": (2, 1),
        "I": (8, 1),
        "O": (9, 1),
        "A": (1.5, 2),
        "S": (2.5, 2),
        "D": (3.5, 2),
        "L": (8.5, 2),
        "Z": (2, 3),
        "X": (3, 3),
        "M": (7, 3),
        ",": (8, 3),
        ".": (9, 3),
        "SHIFT": (0.5, 4),
        "SPACE": (4, 4),
        "ESC": (0, 0),
        "^": (12, 3),
        "<": (11, 4),
        "v": (12, 4),
        ">": (13, 4),
    }

    # Layout parameters — derived from the grid extents so keys always fill the window
    margin_x = 0.01
    margin_y = 0.02
    top_bar_frac = 0.18  # fraction of height reserved for the top info bar

    max_col = max(col for col, row in key_positions.values())  # rightmost column index
    max_row = max(row for col, row in key_positions.values())  # bottommost row index
    h_spacing_ratio = 0.15  # gap as a fraction of key width
    v_spacing_ratio = 0.15  # gap as a fraction of key height

    # Solve: available_width  = (max_col+1) * key_w + max_col * h_gap
    #                         = key_w * ((max_col+1) + max_col * h_spacing_ratio)
    key_width_frac = (1.0 - 2 * margin_x) / ((max_col + 1) + max_col * h_spacing_ratio)
    h_spacing = key_width_frac * h_spacing_ratio

    # Solve: available_height = (max_row+1) * key_h + max_row * v_gap
    key_height_frac = (1.0 - top_bar_frac - margin_y) / ((max_row + 1) + max_row * v_spacing_ratio)
    v_spacing = key_height_frac * v_spacing_ratio

    start_x_frac = margin_x
    start_y_frac = top_bar_frac

    # Derive font sizes from actual key pixel dimensions
    key_h_px = int(key_height_frac * HEIGHT)
    key_w_px = int(key_width_frac * WIDTH)
    font_size = max(10, int(min(key_h_px, key_w_px) * 0.55))
    font = pygame.font.SysFont("Arial Unicode MS", font_size)
    big_font_size = max(10, int(HEIGHT * top_bar_frac * 0.45))
    big_font = pygame.font.SysFont(None, big_font_size)

    keys = []
    for key_code, label, note in key_definitions:
        if label in key_positions:
            col, row = key_positions[label]
            x_frac = start_x_frac + col * (key_width_frac + h_spacing)
            y_frac = start_y_frac + row * (key_height_frac + v_spacing)
            w_frac = key_width_frac * 5 if label == "SPACE" else key_width_frac
            keys.append(
                (key_code, label, note, (x_frac, y_frac, w_frac, key_height_frac))
            )
        else:
            print(f"Warning: No position defined for key {label}")

    pressed_state = {key_code: False for key_code, *_ in keys}
    last_pressed_note = ""

    screen.fill(BLACK)

    # Draw the top note rectangle
    top_rect_w = WIDTH * 0.5
    top_rect_h = HEIGHT * (top_bar_frac * 0.7)
    top_rect_x = (WIDTH - top_rect_w) // 2
    top_rect_y = int(HEIGHT * (top_bar_frac * 0.1))

    pygame.draw.rect(
        screen,
        DARK_GRAY,
        (top_rect_x, top_rect_y, top_rect_w, top_rect_h),
        border_radius=12,
    )
    note_text = last_pressed_note if last_pressed_note else "Press a key"
    note_surf = big_font.render(note_text, True, WHITE)
    note_rect = note_surf.get_rect(center=(WIDTH // 2, top_rect_y + top_rect_h // 2))
    screen.blit(note_surf, note_rect)

    for key_code, label, note, rect_frac in keys:
        x_frac, y_frac, w_frac, h_frac = rect_frac
        x = int(x_frac * WIDTH)
        y = int(y_frac * HEIGHT)
        w = int(w_frac * WIDTH)
        h = int(h_frac * HEIGHT)
        color = GREEN if pressed_state[key_code] else GRAY
        pygame.draw.rect(screen, color, (x, y, w, h), border_radius=8)
        label_surf = font.render(label, True, BLACK)
        label_rect = label_surf.get_rect(center=(x + w / 2, y + h / 2))
        screen.blit(label_surf, label_rect)

    # Flush the initial drawing to screen before any potentially-blocking CAN init
    pygame.display.flip()

    can_net = can_network.CAN_Network()
    controller = KeyboardSenderControl(can_net, dbc_path=DBC_PATH)
    clock = pygame.time.Clock()
    running = True

    while running:
        clock.tick_busy_loop(60)
        controller.parse_events(clock, can_net)

        # Redraw keys to reflect current pressed state
        for key_code, label, note, rect_frac in keys:
            x_frac, y_frac, w_frac, h_frac = rect_frac
            x = int(x_frac * WIDTH)
            y = int(y_frac * HEIGHT)
            w = int(w_frac * WIDTH)
            h = int(h_frac * HEIGHT)
            pressed_state[key_code] = pygame.key.get_pressed()[key_code]
            color = GREEN if pressed_state[key_code] else GRAY
            pygame.draw.rect(screen, color, (x, y, w, h), border_radius=8)
            label_surf = font.render(label, True, BLACK)
            label_rect = label_surf.get_rect(center=(x + w / 2, y + h / 2))
            screen.blit(label_surf, label_rect)

        pygame.display.flip()


def print_key_bindings():
    bindings = [
        ("W / ↑",       "Throttle (hold)"),
        ("S / ↓",       "Brake (hold)"),
        ("A / ←",       "Steer left (hold)"),
        ("D / →",       "Steer right (hold)"),
        ("SPACE",        "Hand brake (hold)"),
        ("Q",            "Toggle reverse gear"),
        ("M",            "Toggle manual gear shift"),
        (", (comma)",    "Gear down  [manual mode]"),
        (". (period)",   "Gear up    [manual mode]"),
        ("O",            "Toggle door open/close"),
        ("L",            "Cycle lights: off → position → low beam → fog"),
        ("Shift + L",    "Toggle high beam"),
        ("Ctrl  + L",    "Toggle special light 1"),
        ("I",            "Toggle interior light"),
        ("Z",            "Toggle left blinker"),
        ("X",            "Toggle right blinker"),
        ("ESC / Ctrl+Q", "Quit"),
    ]
    col_w = max(len(k) for k, _ in bindings) + 2
    print()
    print("  CAN Sender — Key Bindings")
    print("  " + "─" * (col_w + 40))
    for key, desc in bindings:
        print(f"  {key:<{col_w}} {desc}")
    print("  " + "─" * (col_w + 40))
    print()


def main():
    print("Sending commands through CAN bus")
    print_key_bindings()
    try:
        keyboard_parser_loop()
    except KeyboardInterrupt:
        print("\nCancelled by user. Bye!")
        pygame.quit()


if __name__ == "__main__":
    main()
