import carla
import tkinter as tk

import can_network

try:
    import pygame
    from pygame.locals import KMOD_CTRL
    from pygame.locals import KMOD_SHIFT
    from pygame.locals import K_0
    from pygame.locals import K_9
    from pygame.locals import K_BACKQUOTE
    from pygame.locals import K_BACKSPACE
    from pygame.locals import K_COMMA
    from pygame.locals import K_DOWN
    from pygame.locals import K_ESCAPE
    from pygame.locals import K_F1
    from pygame.locals import K_LEFT
    from pygame.locals import K_PERIOD
    from pygame.locals import K_RIGHT
    from pygame.locals import K_SLASH
    from pygame.locals import K_SPACE
    from pygame.locals import K_TAB
    from pygame.locals import K_UP
    from pygame.locals import K_a
    from pygame.locals import K_b
    from pygame.locals import K_c
    from pygame.locals import K_d
    from pygame.locals import K_f
    from pygame.locals import K_g
    from pygame.locals import K_h
    from pygame.locals import K_i
    from pygame.locals import K_l
    from pygame.locals import K_m
    from pygame.locals import K_n
    from pygame.locals import K_o
    from pygame.locals import K_p
    from pygame.locals import K_q
    from pygame.locals import K_r
    from pygame.locals import K_s
    from pygame.locals import K_t
    from pygame.locals import K_v
    from pygame.locals import K_w
    from pygame.locals import K_x
    from pygame.locals import K_z
    from pygame.locals import K_MINUS
    from pygame.locals import K_EQUALS
except ImportError:
    raise RuntimeError('cannot import pygame, make sure pygame package is installed')

class KeyboardSenderControl(object):
    """Class that handles keyboard input."""
    def __init__(self, can_network, start_in_autopilot = False):
        #self._can = can_network
        self._autopilot_enabled = start_in_autopilot
        self._ackermann_enabled = False
        self._ackermann_reverse = 1

        self._control = carla.VehicleControl()
        self._ackermann_control = carla.VehicleAckermannControl()
        self._lights = carla.VehicleLightState.NONE

        self._steer_cache = 0.0

    def _parse_vehicle_keys(self, keys, milliseconds):
        if keys[K_UP] or keys[K_w]:
            if not self._ackermann_enabled:
                self._control.throttle = min(self._control.throttle + 0.1, 1.00)
            else:
                self._ackermann_control.speed += round(milliseconds * 0.005, 2) * self._ackermann_reverse
        else:
            if not self._ackermann_enabled:
                self._control.throttle = 0.0

        if keys[K_DOWN] or keys[K_s]:
            if not self._ackermann_enabled:
                self._control.brake = min(self._control.brake + 0.2, 1)
            else:
                self._ackermann_control.speed -= min(abs(self._ackermann_control.speed), round(milliseconds * 0.005, 2)) * self._ackermann_reverse
                self._ackermann_control.speed = max(0, abs(self._ackermann_control.speed)) * self._ackermann_reverse
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
                    current_lights ^= carla.VehicleLightState.Special1 #TODO: Replace this with CAN messages
                elif event.key == K_l and pygame.key.get_mods() & KMOD_SHIFT:
                    current_lights ^= carla.VehicleLightState.HighBeam #TODO: Replace this with CAN messages
                elif event.key == K_l:
                    # Use 'L' key to switch between lights:
                    # closed -> position -> low beam -> fog
                    if not self._lights & carla.VehicleLightState.Position: #TODO: Replace this with CAN messages
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
                # Gear, Reverse and Manual Gear Control
                if event.key == K_q:
                    if not self._ackermann_enabled:
                        self._control.gear = 1 if self._control.reverse else -1
                    else:
                        self._ackermann_reverse *= -1
                        # Reset ackermann control
                        self._ackermann_control = carla.VehicleAckermannControl()
                elif event.key == K_m:
                    self._control.manual_gear_shift = not self._control.manual_gear_shift
                    #self._control.gear = world.player.get_control().gear # Esse eu preciso entender como que vem
                elif self._control.manual_gear_shift and event.key == K_COMMA:
                    self._control.gear = max(-1, self._control.gear - 1)
                elif self._control.manual_gear_shift and event.key == K_PERIOD:
                    self._control.gear = self._control.gear + 1


        self._parse_vehicle_keys(pygame.key.get_pressed(), clock.get_time())
        self._control.reverse = self._control.gear < 0
        # Set automatic control-related vehicle lights
        if self._control.brake:
            current_lights |= carla.VehicleLightState.Brake
        else: # Remove the Brake flag
            current_lights &= ~carla.VehicleLightState.Brake
        if self._control.reverse:
            current_lights |= carla.VehicleLightState.Reverse
        else: # Remove the Reverse flag
            current_lights &= ~carla.VehicleLightState.Reverse

        if self._lights != current_lights:
            can_network.send_current_lights_msg(current_lights)
            self._lights = current_lights

        can_network.send_msg(self._control)

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
    WIDTH = int(width / 2)
    HEIGHT = int(0.8*int(height / 2))
    screen = pygame.display.set_mode((WIDTH, HEIGHT))

    # Interface related
    # Fonts
    font_size = 36
    font = pygame.font.SysFont('Arial Unicode MS', font_size)
    small_font = pygame.font.SysFont(None, 24)
    big_font = pygame.font.SysFont(None, 48)

    # Colors
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)
    GRAY = (200, 200, 200)
    GREEN = (100, 255, 100)
    DARK_GRAY = (50, 50, 50)

    # Key definitions: (pygame_key_code, label, note)
    key_definitions = [
        (pygame.K_q, 'Q', 'Reverse'),
        (pygame.K_w, 'W', 'Move Forward'),
        (pygame.K_i, 'I', 'Interior Light'),
        (pygame.K_o, 'O', 'Doors'),

        (pygame.K_a, 'A', 'Move Left'),
        (pygame.K_s, 'S', 'Brake'),
        (pygame.K_d, 'D', 'Move Right'),
        (pygame.K_l, 'L', 'Light type'),

        (pygame.K_z, 'Z', 'Left Blinker'),
        (pygame.K_x, 'X', 'Right Blinker'),  # Added X here
        (pygame.K_m, 'M', 'Manual'),
        (pygame.K_COMMA, ',', 'Gear Up'),
        (pygame.K_PERIOD, '.', 'Gear Down'),

        (pygame.K_LSHIFT, 'SHIFT', ''),
        (pygame.K_SPACE, 'SPACE', 'Hand Brake'),
        (pygame.K_ESCAPE, 'ESC', 'Exit'),

        (pygame.K_UP, '^', 'Move Forward'),
        (pygame.K_DOWN, 'v', 'Brake'),
        (pygame.K_LEFT, '<', 'Steer Left'),
        (pygame.K_RIGHT, '>', 'Steer Right'),
    ]

    # Keyboard grid positions → column, row
    # We'll space columns by 1 unit, and rows by 1 unit vertically
    # These are approximate positions matching a QWERTY layout
    key_positions = {
        'Q': (1, 1),
        'W': (2, 1),  # Added W here
        'I': (8, 1),
        'O': (9, 1),

        'A': (1.5, 2),
        'S': (2.5, 2),
        'D': (3.5, 2),
        'L': (8.5, 2),

        'Z': (2, 3),
        'X': (3, 3),  # Added X here
        'M': (7, 3),
        ',': (8, 3),
        '.': (9, 3),

        'SHIFT': (0.5, 4),
        'SPACE': (4, 4),
        'ESC': (0, 0),  # top-left corner (fixed)

        # Arrow keys layout (right side)
        '^': (12, 3),
        '<': (11, 4),
        'v': (12, 4),
        '>': (13, 4),
    }

    # Layout parameters
    key_width_frac = 0.06  # ~6% of screen width
    key_height_frac = 0.1  # ~10% of screen height
    h_spacing = 0.01  # horizontal spacing between keys
    v_spacing = 0.02  # vertical spacing between keys
    start_x_frac = 0.025  # starting x offset
    start_y_frac = 0.15  # starting y offset

    # Build final keys list with positions
    keys = []
    for key_code, label, note in key_definitions:
        if label in key_positions:
            col, row = key_positions[label]
            x_frac = start_x_frac + col * (key_width_frac + h_spacing)
            y_frac = start_y_frac + row * (key_height_frac + v_spacing)

            # Make space key wider
            if label == "SPACE":
                w_frac = key_width_frac * 5
            else:
                w_frac = key_width_frac

            keys.append((key_code, label, note, (x_frac, y_frac, w_frac, key_height_frac)))
        else:
            print(f"Warning: No position defined for key {label}")

    # Track pressed state of each key
    pressed_state = {key_code: False for key_code, *_ in keys}

    # Keep track of the last key pressed (for displaying note)
    last_pressed_note = ""

    # Clear screen
    screen.fill(BLACK)

    # Draw the top note rectangle
    top_rect_w = WIDTH * 0.6
    top_rect_h = HEIGHT * 0.1
    top_rect_x = (WIDTH - top_rect_w) // 2
    top_rect_y = HEIGHT * 0.03

    pygame.draw.rect(screen, DARK_GRAY, (top_rect_x, top_rect_y, top_rect_w, top_rect_h), border_radius=12)
    note_text = last_pressed_note if last_pressed_note else "Press a key"
    note_surf = big_font.render(note_text, True, WHITE)
    note_rect = note_surf.get_rect(center=(WIDTH // 2, top_rect_y + top_rect_h // 2))
    screen.blit(note_surf, note_rect)

    # Draw keys
    for key_code, label, note, rect_frac in keys:
        x_frac, y_frac, w_frac, h_frac = rect_frac
        x = int(x_frac * WIDTH)
        y = int(y_frac * HEIGHT)
        w = int(w_frac * WIDTH)
        h = int(h_frac * HEIGHT)

        color = GREEN if pressed_state[key_code] else GRAY
        pygame.draw.rect(screen, color, (x, y, w, h), border_radius=8)

        # Draw label (centered)
        label_surf = font.render(label, True, BLACK)
        label_rect = label_surf.get_rect(center=(x + w/2, y + h/2))
        screen.blit(label_surf, label_rect)

    can_net = can_network.CAN_Network()
    controller = KeyboardSenderControl(can_net)
    clock = pygame.time.Clock()
    running = True

    while running:
        # Simulator related
        clock.tick_busy_loop(60)
        controller.parse_events(clock, can_net)
        pygame.display.flip()

def main():
    print("Sending commands through CAN bus")
    try:
        keyboard_parser_loop()
    except KeyboardInterrupt:
        print('\nCancelled by user. Bye!')
        pygame.quit()

if __name__ == "__main__":
    main()
