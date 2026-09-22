import json
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


DEFAULT_XBOX_BINDINGS_PATH = "data/xbox_bindings.json"

# Human-readable description of each logical action, shared by the terminal bindings
# table and the on-screen legend so they can never drift out of sync with each other.
ACTION_LABELS = {
    "steer": "Steer",
    "throttle": "Throttle (hold)",
    "brake": "Brake (hold)",
    "hand_brake": "Hand brake (hold)",
    "toggle_door": "Toggle door open/close",
    "cycle_lights": "Cycle lights: off → position → low beam → fog",
    "toggle_manual_gear": "Toggle manual gear shift",
    "toggle_reverse": "Toggle reverse gear",
    "toggle_interior_light": "Toggle interior light",
    "quit": "Quit",
    "toggle_high_beam": "Toggle high beam",
    "toggle_special_light": "Toggle special light 1",
    "gear_up": "Gear up [manual mode]",
    "gear_down": "Gear down [manual mode]",
    "toggle_left_blinker": "Left blinker",
    "toggle_right_blinker": "Right blinker",
}

# Physical button name for each index, per the typical SDL2 Linux Xbox-pad layout.
# This is about the *hardware position*, independent of which action a given index
# is currently bound to — if your pad reports a different layout, check the real
# indices with `python input_devices.py` and use those names/positions instead.
BUTTON_ALIASES = {
    0: "A",
    1: "B",
    2: "X",
    3: "Y",
    4: "LB",
    5: "RB",
    6: "Back",
    7: "Start",
    8: "Guide",
    9: "Left stick click",
    10: "Right stick click",
}

# Env var overrides applied on top of the JSON bindings file, kept for backward
# compatibility with existing scripts/CI that already export these.
_ENV_OVERRIDES = {
    "XBOX_AXIS_STEER": (int, ("axes", "steer")),
    "XBOX_AXIS_THROTTLE": (int, ("axes", "throttle")),
    "XBOX_AXIS_BRAKE": (int, ("axes", "brake")),
    "XBOX_AXIS_DEADZONE": (float, ("axes", "deadzone")),
    "XBOX_HAT_INDEX": (int, ("hat_index",)),
    "XBOX_BTN_DOOR": (int, ("buttons", "toggle_door")),
    "XBOX_BTN_LIGHTS": (int, ("buttons", "cycle_lights")),
    "XBOX_BTN_MANUAL_GEAR": (int, ("buttons", "toggle_manual_gear")),
    "XBOX_BTN_REVERSE": (int, ("buttons", "toggle_reverse")),
    "XBOX_BTN_HAND_BRAKE": (int, ("buttons", "hand_brake")),
    "XBOX_BTN_INTERIOR": (int, ("buttons", "toggle_interior_light")),
    "XBOX_BTN_QUIT": (int, ("buttons", "quit")),
    "XBOX_BTN_HIGH_BEAM": (int, ("buttons", "toggle_high_beam")),
    "XBOX_BTN_SPECIAL_LIGHT": (int, ("buttons", "toggle_special_light")),
}


def load_xbox_bindings(path=None):
    """Load the Xbox button/axis mapping from a JSON file, with env var overrides.

    Verify indices against the real pad with `python input_devices.py` and either
    edit the JSON file or override individual entries via the XBOX_* env vars if
    the driver/layout differs.
    """
    path = path or DEFAULT_XBOX_BINDINGS_PATH
    try:
        with open(path) as f:
            bindings = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise RuntimeError(
            f"Failed to load Xbox bindings from '{path}' ({e}). "
            "Pass a valid file via --xbox-bindings."
        )

    for env_var, (cast, keys) in _ENV_OVERRIDES.items():
        raw = os.environ.get(env_var)
        if raw is None:
            continue
        target = bindings
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = cast(raw)

    seen = {}
    for action, index in bindings["buttons"].items():
        if index in seen:
            raise ValueError(
                f"Xbox bindings conflict: '{seen[index]}' and '{action}' are both "
                f"mapped to button {index}"
            )
        seen[index] = action

    return bindings


def xbox_legend_rows(bindings):
    """Flatten a loaded bindings dict into display rows shared by the terminal
    table and the on-screen legend, each carrying enough info to poll live state."""
    axes = bindings["axes"]
    rows = [
        {"descriptor": "Left stick", "action": "steer", "kind": "axis", "index": axes["steer"]},
        {"descriptor": "Right trigger (RT)", "action": "throttle", "kind": "axis", "index": axes["throttle"]},
        {"descriptor": "Left trigger (LT)", "action": "brake", "kind": "axis", "index": axes["brake"]},
    ]
    for action, index in sorted(bindings["buttons"].items(), key=lambda item: item[1]):
        name = BUTTON_ALIASES.get(index)
        descriptor = f"{name} (button {index})" if name else f"Button {index}"
        rows.append({"descriptor": descriptor, "action": action, "kind": "button", "index": index})
    for direction, (dx, dy) in (
        ("up", (0, 1)),
        ("down", (0, -1)),
        ("left", (-1, 0)),
        ("right", (1, 0)),
    ):
        action = bindings["dpad"].get(direction)
        if action is not None:
            rows.append({
                "descriptor": f"D-pad {direction}",
                "action": action,
                "kind": "hat",
                "direction": (dx, dy),
            })
    for row in rows:
        row["label"] = ACTION_LABELS.get(row["action"], row["action"].replace("_", " ").title())
    return rows


class XboxInputDevice(object):
    """Reads Xbox controller state/events and exposes them as logical driving actions."""

    def __init__(self, joystick_index=0, bindings_path=None):
        self.bindings = load_xbox_bindings(bindings_path)

        pygame.joystick.init()
        if pygame.joystick.get_count() <= joystick_index:
            raise RuntimeError("No Xbox controller detected")
        self._joystick = pygame.joystick.Joystick(joystick_index)
        self._joystick.init()

        axes = self.bindings["axes"]
        self._axis_steer = axes["steer"]
        self._axis_throttle = axes["throttle"]
        self._axis_brake = axes["brake"]
        self._axis_deadzone = axes["deadzone"]
        self._hat_index = self.bindings["hat_index"]

        buttons = self.bindings["buttons"]
        self._hand_brake_button = buttons.get("hand_brake")
        self._button_actions = {
            index: action for action, index in buttons.items() if action != "hand_brake"
        }
        self._dpad_actions = dict(self.bindings["dpad"])

    @property
    def joystick(self):
        return self._joystick

    def poll_actions(self):
        actions = []
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                actions.append("quit")
            elif event.type == pygame.JOYDEVICEREMOVED:
                actions.append("quit")
            elif event.type == pygame.JOYBUTTONDOWN:
                action = self._button_actions.get(event.button)
                if action is not None:
                    actions.append(action)
            elif event.type == pygame.JOYHATMOTION and event.hat == self._hat_index:
                x, y = event.value
                if y == 1:
                    action = self._dpad_actions.get("up")
                elif y == -1:
                    action = self._dpad_actions.get("down")
                elif x == -1:
                    action = self._dpad_actions.get("left")
                elif x == 1:
                    action = self._dpad_actions.get("right")
                else:
                    action = None
                if action is not None:
                    actions.append(action)
        return actions

    def get_axes(self, milliseconds):
        throttle = _apply_deadzone(
            (self._joystick.get_axis(self._axis_throttle) + 1) / 2, self._axis_deadzone
        )
        brake = _apply_deadzone(
            (self._joystick.get_axis(self._axis_brake) + 1) / 2, self._axis_deadzone
        )
        steer = _apply_deadzone(self._joystick.get_axis(self._axis_steer), self._axis_deadzone)
        steer = min(0.7, max(-0.7, steer))

        return {
            "throttle": max(0.0, min(1.0, throttle)),
            "brake": max(0.0, min(1.0, brake)),
            "steer": round(steer, 1),
            "hand_brake": bool(
                self._hand_brake_button is not None
                and self._joystick.get_button(self._hand_brake_button)
            ),
        }

    def is_row_active(self, row):
        """Poll current live state for a legend row built by xbox_legend_rows()."""
        if row["kind"] == "axis":
            raw = self._joystick.get_axis(row["index"])
            value = (raw + 1) / 2 if row["action"] in ("throttle", "brake") else raw
            return _apply_deadzone(value, self._axis_deadzone) != 0.0
        if row["kind"] == "button":
            return bool(self._joystick.get_button(row["index"]))
        if row["kind"] == "hat":
            return self._joystick.get_hat(self._hat_index) == row["direction"]
        return False


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
        print("Loaded bindings:", device.bindings)
        print("Move sticks / triggers / press buttons, Ctrl+C to exit...")
        clock = pygame.time.Clock()
        while True:
            for action in device.poll_actions():
                print("action:", action)
            print(device.get_axes(clock.get_time()))
            clock.tick(10)
