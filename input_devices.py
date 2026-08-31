import os

try:
    import pygame
    from pygame.locals import (
        K_COMMA,
        K_DOWN,
        K_LEFT,
        K_PERIOD,
        K_RIGHT,
        K_SPACE,
        K_UP,
        KMOD_CTRL,
        KMOD_SHIFT,
        K_ESCAPE,
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


def _apply_deadzone(value, deadzone):
    return 0.0 if abs(value) < deadzone else value


class KeyboardInputDevice(object):
    """Reads raw keyboard state/events and exposes them as logical driving actions."""

    def __init__(self):
        self._steer_cache = 0.0
        self._throttle = 0.0
        self._brake = 0.0

    def poll_actions(self):
        actions = []
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                actions.append("quit")
            elif event.type == pygame.KEYUP:
                if event.key == K_ESCAPE or (
                    event.key == K_q and pygame.key.get_mods() & KMOD_CTRL
                ):
                    actions.append("quit")
                elif event.key == K_o:
                    actions.append("toggle_door")
                elif event.key == K_l and pygame.key.get_mods() & KMOD_CTRL:
                    actions.append("toggle_special_light")
                elif event.key == K_l and pygame.key.get_mods() & KMOD_SHIFT:
                    actions.append("toggle_high_beam")
                elif event.key == K_l:
                    actions.append("cycle_lights")
                elif event.key == K_i:
                    actions.append("toggle_interior_light")
                elif event.key == K_z:
                    actions.append("toggle_left_blinker")
                elif event.key == K_x:
                    actions.append("toggle_right_blinker")
                elif event.key == K_q:
                    actions.append("toggle_reverse")
                elif event.key == K_m:
                    actions.append("toggle_manual_gear")
                elif event.key == K_COMMA:
                    actions.append("gear_down")
                elif event.key == K_PERIOD:
                    actions.append("gear_up")
        return actions

    def get_axes(self, milliseconds):
        keys = pygame.key.get_pressed()

        if keys[K_UP] or keys[K_w]:
            self._throttle = min(self._throttle + 0.1, 1.00)
        else:
            self._throttle = 0.0

        if keys[K_DOWN] or keys[K_s]:
            self._brake = min(self._brake + 0.2, 1.0)
        else:
            self._brake = 0.0

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

        return {
            "throttle": self._throttle,
            "brake": self._brake,
            "steer": round(self._steer_cache, 1),
            "hand_brake": bool(keys[K_SPACE]),
        }


# Tunable Xbox mapping (typical SDL2 Linux Xbox-pad layout). Verify against the real pad
# with `python input_devices.py` and override via env vars if the driver differs.
AXIS_STEER = int(os.environ.get("XBOX_AXIS_STEER", 0))
AXIS_THROTTLE = int(os.environ.get("XBOX_AXIS_THROTTLE", 5))
AXIS_BRAKE = int(os.environ.get("XBOX_AXIS_BRAKE", 2))
AXIS_DEADZONE = float(os.environ.get("XBOX_AXIS_DEADZONE", "0.15"))
HAT_INDEX = int(os.environ.get("XBOX_HAT_INDEX", 0))

BTN_DOOR = int(os.environ.get("XBOX_BTN_DOOR", 0))  # A
BTN_LIGHTS = int(os.environ.get("XBOX_BTN_LIGHTS", 1))  # B
BTN_MANUAL_GEAR = int(os.environ.get("XBOX_BTN_MANUAL_GEAR", 2))  # X
BTN_REVERSE = int(os.environ.get("XBOX_BTN_REVERSE", 3))  # Y
BTN_HAND_BRAKE = int(os.environ.get("XBOX_BTN_HAND_BRAKE", 4))  # LB (held)
BTN_INTERIOR = int(os.environ.get("XBOX_BTN_INTERIOR", 6))  # Back/View
BTN_QUIT = int(os.environ.get("XBOX_BTN_QUIT", 7))  # Start
BTN_HIGH_BEAM = int(os.environ.get("XBOX_BTN_HIGH_BEAM", 9))  # Left stick click
BTN_SPECIAL_LIGHT = int(os.environ.get("XBOX_BTN_SPECIAL_LIGHT", 10))  # Right stick click

_BUTTON_ACTIONS = {
    BTN_DOOR: "toggle_door",
    BTN_LIGHTS: "cycle_lights",
    BTN_MANUAL_GEAR: "toggle_manual_gear",
    BTN_REVERSE: "toggle_reverse",
    BTN_INTERIOR: "toggle_interior_light",
    BTN_QUIT: "quit",
    BTN_HIGH_BEAM: "toggle_high_beam",
    BTN_SPECIAL_LIGHT: "toggle_special_light",
}


class XboxInputDevice(object):
    """Reads Xbox controller state/events and exposes them as logical driving actions."""

    def __init__(self, joystick_index=0):
        pygame.joystick.init()
        if pygame.joystick.get_count() <= joystick_index:
            raise RuntimeError("No Xbox controller detected")
        self._joystick = pygame.joystick.Joystick(joystick_index)
        self._joystick.init()

    def poll_actions(self):
        actions = []
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                actions.append("quit")
            elif event.type == pygame.JOYDEVICEREMOVED:
                actions.append("quit")
            elif event.type == pygame.JOYBUTTONDOWN:
                action = _BUTTON_ACTIONS.get(event.button)
                if action is not None:
                    actions.append(action)
            elif event.type == pygame.JOYHATMOTION and event.hat == HAT_INDEX:
                x, y = event.value
                if y == 1:
                    actions.append("gear_up")
                elif y == -1:
                    actions.append("gear_down")
                elif x == -1:
                    actions.append("toggle_left_blinker")
                elif x == 1:
                    actions.append("toggle_right_blinker")
        return actions

    def get_axes(self, milliseconds):
        throttle = _apply_deadzone(
            (self._joystick.get_axis(AXIS_THROTTLE) + 1) / 2, AXIS_DEADZONE
        )
        brake = _apply_deadzone(
            (self._joystick.get_axis(AXIS_BRAKE) + 1) / 2, AXIS_DEADZONE
        )
        steer = _apply_deadzone(self._joystick.get_axis(AXIS_STEER), AXIS_DEADZONE)
        steer = min(0.7, max(-0.7, steer))

        return {
            "throttle": max(0.0, min(1.0, throttle)),
            "brake": max(0.0, min(1.0, brake)),
            "steer": round(steer, 1),
            "hand_brake": bool(self._joystick.get_button(BTN_HAND_BRAKE)),
        }


if __name__ == "__main__":
    assert _apply_deadzone(0.05, 0.15) == 0.0
    assert _apply_deadzone(0.20, 0.15) == 0.20
    assert _apply_deadzone(-0.05, 0.15) == 0.0

    os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
    pygame.init()
    pygame.joystick.init()
    pygame.display.set_mode((300, 100))  # SDL needs a display surface to pump joystick events

    if pygame.joystick.get_count() == 0:
        print("No joystick detected. Plug in the Xbox controller and re-run.")
    else:
        device = XboxInputDevice()
        print(f"Connected: {device._joystick.get_name()}")
        print("Move sticks / triggers / press buttons, Ctrl+C to exit...")
        clock = pygame.time.Clock()
        while True:
            for action in device.poll_actions():
                print("action:", action)
            print(device.get_axes(clock.get_time()))
            clock.tick(10)
