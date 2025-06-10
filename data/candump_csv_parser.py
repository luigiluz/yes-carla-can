import pandas as pd

CANDUMP_FILEPATH = "/home/luigi/workspace/nerd_for_speed/data/carla_can_bus.log"

def main():
    print("candump csv parser")

    # Open the candump file
    with open(CANDUMP_FILEPATH, 'r') as file:
        lines = file.readlines()

    # Parse the lines into a DataFrame
    data = []
    for line in lines:
        parts = line.strip().split()
        if len(parts) >= 3:
            timestamp = parts[0].replace("(", "").replace(")", "")
            bus = parts[1]
            data_bytes = ' '.join(parts[2:])
            can_id = data_bytes.split("#")[0]
            payload = data_bytes.split("#")[1]
            data.append({'timestamp': timestamp, 'bus': bus, 'can_id': can_id, 'payload': payload})

    # Export to a DataFrame
    df = pd.DataFrame(data)

    # Export to csv
    df.to_csv('candump_parsed.csv', index=False)
    print("candump csv parser finished. Data exported to candump_parsed.csv")

if __name__ == "__main__":
    main()
