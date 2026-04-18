import cantools

# Single source of truth for every message the system knows about.
# Format: "MESSAGE_NAME": (signal_name, send_method, required)
#   signal_name  — expected DBC signal name (None if the message has no encodable signal)
#   send_method  — CAN_Network method that sends it (None if event-driven only)
#   required     — True if the system cannot operate without this message
MESSAGES = {
    "THROTTLE":            ("THROTTLE_signal",            "send_throttle_msg",            True),
    "BRAKE":               ("BRAKE_signal",               "send_brake_msg",               True),
    "STEER":               ("STEER_signal",               "send_steer_msg",               True),
    "REVERSE":             ("REVERSE_signal",             "send_reverse_msg",             True),
    "HAND_BRAKE":          ("HAND_BRAKE_signal",          "send_hand_brake_msg",          True),
    "MANUAL_TRANSMISSION": ("MANUAL_TRANSMISSION_signal", "send_manual_transmission_msg", True),
    "GEAR":                ("GEAR_signal",                "send_gear_msg",                True),
    "AUTOPILOT":           (None,                         "send_autopilot_msg",           False),
    "DOORS":               ("DOORS_signal",               "send_switch_door_state_msg",  False),
    "GENERAL_LIGHTS":      ("GENERAL_LIGHTS_signal",      "send_current_lights_msg",     False),
}

# Derived constants — do not edit these; edit MESSAGES above instead.
REQUIRED_MESSAGES = frozenset(name for name, (_, _, required) in MESSAGES.items() if required)
SUPPORTED_MESSAGES = frozenset(MESSAGES.keys())
REQUIRED_SIGNALS   = {name: sig     for name, (sig, _, _)      in MESSAGES.items() if sig is not None}
MESSAGE_SENDERS    = {name: method  for name, (_, method, _)   in MESSAGES.items() if method is not None}


def load_and_validate(dbc_path):
    """
    Load a DBC file and validate it against the set of supported messages.

    - Raises ValueError  if any REQUIRED_MESSAGES are absent.
    - Raises ValueError  if a supported message has the wrong signal name or more than one signal.
    - Prints a WARNING   if required messages have no cycle time (won't be sent periodically).
    - Prints an INFO     if the DBC contains messages the system doesn't handle.

    Returns:
        db          — the loaded cantools database object
        cycle_times — dict of {message_name: interval_seconds} for periodic messages
    """
    db = cantools.database.load_file(dbc_path)
    db_names = {msg.name for msg in db.messages}

    # Fatal: required messages missing from DBC.
    missing_required = REQUIRED_MESSAGES - db_names
    if missing_required:
        raise ValueError(
            f"[CAN] DBC '{dbc_path}' is missing required messages: "
            f"{sorted(missing_required)}"
        )

    # Fatal: signal name or single-signal contract mismatch for any supported message.
    for msg_name, expected_signal in REQUIRED_SIGNALS.items():
        if msg_name not in db_names:
            continue  # already caught above for required ones; optional ones can be absent
        dbc_msg = db.get_message_by_name(msg_name)
        actual_signals = [s.name for s in dbc_msg.signals]
        if len(actual_signals) != 1:
            raise ValueError(
                f"[CAN] Message '{msg_name}' must have exactly 1 signal, "
                f"found {len(actual_signals)}: {actual_signals}"
            )
        if actual_signals[0] != expected_signal:
            raise ValueError(
                f"[CAN] Message '{msg_name}' signal mismatch: "
                f"expected '{expected_signal}', found '{actual_signals[0]}'"
            )

    # Informational: DBC has messages the system doesn't handle.
    unhandled = db_names - SUPPORTED_MESSAGES
    if unhandled:
        print(
            f"[CAN] INFO: DBC contains messages not handled by this module "
            f"(will be ignored): {sorted(unhandled)}"
        )

    # Extract cycle times for supported periodic messages.
    cycle_times = {}
    for msg in db.messages:
        if msg.name in SUPPORTED_MESSAGES and msg.cycle_time and msg.cycle_time > 0:
            cycle_times[msg.name] = msg.cycle_time / 1000.0  # ms → seconds

    # Warning: required messages with no cycle time won't be sent periodically.
    no_period = REQUIRED_MESSAGES - set(cycle_times)
    if no_period:
        print(
            f"[CAN] WARNING: The following required messages have no cycle time "
            f"in the DBC and will NOT be sent periodically: {sorted(no_period)}"
        )

    return db, cycle_times
