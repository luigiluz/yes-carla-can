import argparse
import can
from pathlib import Path
from defense.id_time_intrusion_detection import IdTimeIntrusionDetection

DETECTOR_FACTORY = {
    "id_time": IdTimeIntrusionDetection
}

DATA_PATH = Path(__file__).parent / "data" / "can_ids_statistics_periodic_0.2.json"

def main():
    print("Intrusion Detection System for CAN Bus")

    parser = argparse.ArgumentParser(description="Intrusion Detection System for CAN Bus")
    parser.add_argument("--detector", type=str, required=True, help="CAN ID to monitor")

    args = parser.parse_args()

    selected_detector = DETECTOR_FACTORY[args.detector]()
    selected_detector.load(DATA_PATH)
    bus = can.interface.Bus(channel='vcan0', interface='socketcan')

    try:
        while True:
            msg = bus.recv(timeout=0)
            if msg is not None:
                selected_detector.run(msg)
    except KeyboardInterrupt:
        print("Attack stopped by user.")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
