import argparse
import can
from pathlib import Path
from defense.id_time_intrusion_detection import IdTimeIntrusionDetection
from defense.ids_training.ml_intrusion_detection import MlIntrusionDetection
from can_network import VCAN_CHANNEL, CAN_INTERFACE

DETECTOR_FACTORY = {
    "id_time": IdTimeIntrusionDetection,
    "ml":      MlIntrusionDetection,
}

DEFAULT_DATA_PATH = Path(__file__).parent / "traffic_logs" / "logs_for_ml_ids_training_parsed_statistics.json"

def main():
    print("Intrusion Detection System for CAN Bus")

    parser = argparse.ArgumentParser(description="Intrusion Detection System for CAN Bus")
    parser.add_argument("--detector", type=str, required=True, choices=DETECTOR_FACTORY.keys(),
                        help=f"Intrusion detection algorithm to use. Available options: {', '.join(DETECTOR_FACTORY.keys())}")
    parser.add_argument("--id-time-statistics", type=Path, default=DEFAULT_DATA_PATH,
                        help=f"Path to the baseline statistics JSON file used by the id_time detector (default: {DEFAULT_DATA_PATH})")
    parser.add_argument("--ml-model", type=Path, default=None,
                        help="Path to the trained Isolation Forest PKL file (required when --detector ml)")

    args = parser.parse_args()

    if args.detector == "ml" and args.ml_model is None:
        parser.error("--ml-model is required when using --detector ml")

    selected_detector = DETECTOR_FACTORY[args.detector]()
    model_path = args.ml_model if args.detector == "ml" else args.id_time_statistics
    selected_detector.load(model_path)
    bus = can.interface.Bus(channel=VCAN_CHANNEL, interface=CAN_INTERFACE)

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
