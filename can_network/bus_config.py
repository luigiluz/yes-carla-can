import os

CAN_INTERFACE = os.environ.get("CAN_INTERFACE", "socketcan")
VCAN_CHANNEL = os.environ.get("CAN_CHANNEL", "vcan0")
VCAN_ATTACKER_CHANNEL = os.environ.get("CAN_ATTACKER_CHANNEL", "vcan1")


def bus_kwargs(channel=None, serial=None, **overrides):
    """Resolve can.Bus/can.ThreadSafeBus kwargs, independent of the backend in use."""
    kwargs = {
        "interface": CAN_INTERFACE,
        "channel": channel or VCAN_CHANNEL,
        "receive_own_messages": True,
    }
    if CAN_INTERFACE == "ics_neovi":
        serial = serial or os.environ.get("CAN_SERIAL")
        if serial:
            kwargs["serial"] = serial
        if os.environ.get("CAN_BITRATE"):
            kwargs["bitrate"] = int(os.environ["CAN_BITRATE"])
    kwargs.update(overrides)
    return kwargs
