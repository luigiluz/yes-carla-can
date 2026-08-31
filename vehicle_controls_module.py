import os
import signal
import sys
import time
import tkinter as tk

import carla

import can_network
from can_network import VCAN_CHANNEL
from can_network.dbc import MESSAGE_SENDERS, BUS_ASSIGNMENT
from input_devices import (
    KeyboardInputDevice,
    XboxInputDevice,
    load_xbox_bindings,
    xbox_legend_rows,
)

try:
    import pygame
except ImportError:
    raise RuntimeError("cannot import pygame, make sure pygame package is installed")


class VehicleSenderControl(object):
    """Reads driving input from an input_device and periodically sends CAN messages."""

    def __init__(self, powertrain_ecu, comfort_ecu, input_device, start_in_autopilot=False):
        self._autopilot_enabled = start_in_autopilot
        self._input_device = input_device

        self._ecus = {"POWERTRAIN": powertrain_ecu, "COMFORT": comfort_ecu}

        self._control = carla.VehicleControl()
        self._lights = carla.VehicleLightState.NONE

        # Build per-message timers from cycle times already loaded by each ECU.
        now = time.time()
        # _msg_timers: {msg_name: [interval_seconds, last_sent_timestamp]}
        self._msg_timers = {
            name: [interval, now]
            for ecu in (powertrain_ecu, comfort_ecu)
            for name, interval in ecu.cycle_times.items()
            if name in MESSAGE_SENDERS
        }

    # ------------------------------------------------------------------
    # Periodic sending
    # ------------------------------------------------------------------

    def _send_periodic_messages(self):
        """Fire each message independently according to its DBC cycle time."""
        now = time.time()
        for msg_name, (interval, last_sent) in self._msg_timers.items():
            if now - last_sent >= interval:
                ecu = self._ecus[BUS_ASSIGNMENT[msg_name]]
                method = getattr(ecu, MESSAGE_SENDERS[msg_name], None)
                if method is not None:
                    try:
                        method(self._control)
                    except Exception as e:
                        print(f"[CAN] Failed to send {msg_name}: {e}")
                else:
                    print(
                        f"[CAN] Method {MESSAGE_SENDERS[msg_name]} not found on CAN_Network"
                    )
                self._msg_timers[msg_name][1] = now

    # ------------------------------------------------------------------
    # Input parsing (device-agnostic)
    # ------------------------------------------------------------------

    def parse_events(self, clock):
        comfort_ecu = self._ecus["COMFORT"]
        current_lights = self._lights

        for action in self._input_device.poll_actions():
            if action == "quit":
                return True
            elif action == "toggle_door":
                try:
                    comfort_ecu.send_switch_door_state_msg()
                except:
                    pass
            elif action == "toggle_special_light":
                current_lights ^= carla.VehicleLightState.Special1
            elif action == "toggle_high_beam":
                current_lights ^= carla.VehicleLightState.HighBeam
            elif action == "cycle_lights":
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
            elif action == "toggle_interior_light":
                current_lights ^= carla.VehicleLightState.Interior
            elif action == "toggle_left_blinker":
                current_lights ^= carla.VehicleLightState.LeftBlinker
            elif action == "toggle_right_blinker":
                current_lights ^= carla.VehicleLightState.RightBlinker
            elif action == "toggle_reverse":
                self._control.gear = 1 if self._control.reverse else -1
            elif action == "toggle_manual_gear":
                self._control.manual_gear_shift = not self._control.manual_gear_shift
            elif action == "gear_down":
                if self._control.manual_gear_shift:
                    self._control.gear = max(-1, self._control.gear - 1)
            elif action == "gear_up":
                if self._control.manual_gear_shift:
                    self._control.gear = self._control.gear + 1

        axes = self._input_device.get_axes(clock.get_time())
        self._control.throttle = axes["throttle"]
        self._control.brake = axes["brake"]
        self._control.steer = axes["steer"]
        self._control.hand_brake = axes["hand_brake"]
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
            comfort_ecu.send_current_lights_msg(current_lights)
            self._lights = current_lights

        # Periodic: send each message according to its DBC cycle time
        self._send_periodic_messages()


def run_parser_loop(input_mode, dbc_path="data/carla.dbc", powertrain_channel=None, comfort_channel=None, can_serial=None, xbox_bindings_path=None):
    print(f"Starting {input_mode} parser loop")
    pygame.init()
    pygame.font.init()

    input_device = (
        KeyboardInputDevice()
        if input_mode == "keyboard"
        else XboxInputDevice(bindings_path=xbox_bindings_path)
    )

    # Colors shared by both the keyboard widget and the Xbox legend
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)
    GRAY = (200, 200, 200)
    GREEN = (100, 255, 100)
    DARK_GRAY = (50, 50, 50)

    keys = []
    if input_mode == "keyboard":
        root = tk.Tk()
        width = root.winfo_screenwidth()
        height = root.winfo_screenheight()
        root.destroy()
        print(f"width: {width}, height: {height}")
        WIDTH = int(width * 0.45)
        HEIGHT = int(height * 0.33)
        screen = pygame.display.set_mode((WIDTH, HEIGHT))

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
    else:
        legend_rows = xbox_legend_rows(input_device.bindings)

        ROW_H = 26
        WIDTH, HEIGHT = 460, 50 + ROW_H * len(legend_rows)
        screen = pygame.display.set_mode((WIDTH, HEIGHT))
        font = pygame.font.SysFont(None, 20)
        title_font = pygame.font.SysFont(None, 24)

        def draw_xbox_legend():
            screen.fill(BLACK)
            title = title_font.render(f"Xbox: {input_device.joystick.get_name()}", True, WHITE)
            screen.blit(title, (10, 8))
            y = 40
            for row in legend_rows:
                color = GREEN if input_device.is_row_active(row) else GRAY
                pygame.draw.rect(screen, color, (10, y, WIDTH - 20, ROW_H - 4), border_radius=6)
                text = font.render(f"{row['descriptor']}: {row['label']}", True, BLACK)
                screen.blit(text, text.get_rect(center=(WIDTH // 2, y + (ROW_H - 4) // 2)))
                y += ROW_H
            pygame.display.flip()

        draw_xbox_legend()

    bundle = can_network.open_ecu_bundle(dbc_path, powertrain_channel, comfort_channel, serial=can_serial)
    powertrain_ecu, comfort_ecu = bundle.powertrain, bundle.comfort
    controller = VehicleSenderControl(powertrain_ecu, comfort_ecu, input_device)
    scheduled = [f"{name}({int(iv[0] * 1000)}ms)" for name, iv in sorted(controller._msg_timers.items())]
    print(f"[CAN] DBC loaded: {dbc_path}")
    print(f"[CAN] Periodic messages scheduled: {' '.join(scheduled)}")
    clock = pygame.time.Clock()
    running = True

    while running:
        clock.tick_busy_loop(60)
        # Drain the bus's RX/echo queue even though we don't act on it here — on the
        # physical (Intrepid) backend, letting it go unread stalls sends after a while.
        bundle.poll()
        if controller.parse_events(clock):
            running = False
            break

        if input_mode == "keyboard":
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
        else:
            draw_xbox_legend()

    pygame.quit()
    sys.exit(0)


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


def print_xbox_bindings(bindings_path=None):
    loaded = load_xbox_bindings(bindings_path)
    bindings = [(row["descriptor"], row["label"]) for row in xbox_legend_rows(loaded)]
    col_w = max(len(k) for k, _ in bindings) + 2
    print()
    print("  CAN Sender — Xbox Controller Bindings")
    print("  " + "─" * (col_w + 40))
    for key, desc in bindings:
        print(f"  {key:<{col_w}} {desc}")
    print("  " + "─" * (col_w + 40))
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
        "--powertrain-channel",
        default=VCAN_CHANNEL,
        help=f"CAN channel/interface name for the POWERTRAIN-bus ECU, virtual or physical "
        f"(default: {VCAN_CHANNEL})",
    )
    parser.add_argument(
        "--comfort-channel",
        default=VCAN_CHANNEL,
        help=f"CAN channel/interface name for the COMFORT-bus ECU, virtual or physical "
        f"(default: {VCAN_CHANNEL})",
    )
    parser.add_argument(
        "--can-serial",
        default=None,
        help="Serial number of the physical CAN device shared by both ECUs (physical mode "
        "only; defaults to the CAN_SERIAL env var, then auto-detect)",
    )
    parser.add_argument(
        "--input",
        choices=["keyboard", "xbox"],
        default="keyboard",
        help="Input device used to drive the vehicle (default: keyboard)",
    )
    parser.add_argument(
        "--xbox-bindings",
        default="data/xbox_bindings.json",
        help="Path to the Xbox controller button/axis mapping JSON file "
        "(default: data/xbox_bindings.json). Ignored in keyboard mode. Individual "
        "entries can still be overridden with XBOX_* env vars.",
    )
    args = parser.parse_args()

    if args.input == "xbox":
        # Must be set before pygame.init() (called inside run_parser_loop) or SDL only
        # delivers joystick input while the pygame window has OS focus.
        os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")

    # Ensure SIGTERM (e.g. from environment_down.sh) also exits cleanly
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    print("Sending commands through CAN bus")
    if args.input == "keyboard":
        print_key_bindings()
    else:
        print_xbox_bindings(args.xbox_bindings)
    try:
        run_parser_loop(
            args.input,
            dbc_path=args.dbc,
            powertrain_channel=args.powertrain_channel,
            comfort_channel=args.comfort_channel,
            can_serial=args.can_serial,
            xbox_bindings_path=args.xbox_bindings,
        )
    except (KeyboardInterrupt, SystemExit):
        print("\nCancelled by user. Bye!")
        pygame.quit()
        sys.exit(0)


if __name__ == "__main__":
    main()
