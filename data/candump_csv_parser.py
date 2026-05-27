import argparse
import pandas as pd


PAYLOAD_BYTES = 8


def main():
    parser = argparse.ArgumentParser(description="Parse a candump log file into a CSV.")
    parser.add_argument(
        "--input",
        default="candump-2026-04-17_225932.log",
        help="Path to the candump .log file to parse (default: candump-2026-04-17_225932.log)",
    )
    args = parser.parse_args()

    print("candump csv parser")

    # Open the candump file
    with open(args.input, 'r') as file:
        lines = file.readlines()

    # Parse the lines into a DataFrame
    data = []
    for line in lines:
        parts = line.strip().split()
        if len(parts) >= 3:
            timestamp = parts[0].replace("(", "").replace(")", "")
            bus = parts[1]
            data_bytes = ' '.join(parts[2:])
            if "#" not in data_bytes:
                continue

            can_id, payload_hex = data_bytes.split("#", 1)

            row = {
                'timestamp': timestamp,
                'bus': bus,
                'can_id': can_id,
            }

            for i in range(PAYLOAD_BYTES):
                start = i * 2
                end = start + 2
                row[f'payload_byte_{i}'] = payload_hex[start:end] if len(payload_hex) >= end else None

            data.append(row)

    # Export to a DataFrame
    df = pd.DataFrame(data)

    # Export to csv
    filename = args.input.rsplit('.', 1)[0] + '_parsed'
    df.to_csv(f'{filename}.csv', index=False)
    print(f"candump csv parser finished. Data exported to {filename}.csv")

if __name__ == "__main__":
    main()
