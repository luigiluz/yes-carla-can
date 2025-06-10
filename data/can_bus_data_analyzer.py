import pandas as pd
import json

def main():
    print("Analyzing CAN bus data")

    df = pd.read_csv('candump_parsed.csv')
    print(df.head(5))
    print(df.info())

    unique_can_ids = df['can_id'].unique()

    print(f"Unique CAN IDs: {df['can_id'].unique()}")

    can_ids_statistics_dict = {}

    for can_id in unique_can_ids:
        can_id_df = df.loc[df['can_id'] == can_id]
        # Take the subsequent difference of the timestamp column
        can_id_df.loc[:, 'timestamp_diff'] = can_id_df.loc[:, 'timestamp'].diff().fillna(0)
        # Make the mean and std of the timestamp_diff column
        mean_diff = can_id_df['timestamp_diff'].mean()
        std_diff = can_id_df['timestamp_diff'].std()
        #print(f"CAN ID: {can_id}, Mean Timestamp Diff: {mean_diff}, Std Dev: {std_diff}")

        msg_type = "periodic" if std_diff < 0.01 else "sporadic"

        can_ids_statistics_dict[can_id] = {
            'mean_timestamp_diff': mean_diff,
            'std_timestamp_diff': std_diff,
            "mgs_type": msg_type
        }

    print(f"CAN IDs Statistics: {json.dumps(can_ids_statistics_dict, indent=4)}")

    # Export to JSON
    with open('can_ids_statistics.json', 'w') as f:
        json.dump(can_ids_statistics_dict, f, indent=4)


if __name__ == "__main__":
    main()
