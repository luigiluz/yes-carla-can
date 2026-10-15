import argparse
import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest

ALGORITHM = "isolation_forest"
FEATURE_COLS = ["can_id"] + [f"payload_byte_{i}" for i in range(8)]
OUTPUT_DIR = Path(__file__).parent / "models"


def _parse_hex(x) -> int:
    """Parse a hex value that may be a string, int, or float (pandas dtype inference)."""
    if pd.isna(x):
        return 0
    # pandas reads "00" as 0.0 when the column has NaN rows; strip decimal suffix
    return int(str(x).split(".")[0], 16)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Convert hex string columns to integers suitable for model input."""
    X = pd.DataFrame()
    X["can_id"] = df["can_id"].apply(_parse_hex)
    for col in [f"payload_byte_{i}" for i in range(8)]:
        X[col] = df[col].apply(_parse_hex)
    return X


def main():
    parser = argparse.ArgumentParser(
        description="Train an Isolation Forest IDS model from a parsed CAN bus CSV."
    )
    parser.add_argument("--csv",  type=Path, required=True,
                        help="Path to the parsed candump CSV (output of candump_csv_parser.py)")
    parser.add_argument("--dbc",  type=Path, required=True,
                        help="Path to the DBC file used to generate the log (used for output naming)")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR,
                        help=f"Directory to save the trained model PKL (default: {OUTPUT_DIR})")
    parser.add_argument("--ignore-label", action="store_true",
                        help="Skip the normal-traffic label check. candump_csv_parser.py fills 'label' "
                             "from the candump T/R direction flag, not ground truth, so logs where the "
                             "ECU received frames (R) would otherwise be rejected as attack data.")
    parser.add_argument("--exclude-ids", default="",
                        help="Comma-separated hex CAN IDs to leave out of the model, e.g. continuous sensor "
                             "IDs (GNSS/IMU) whose raw payload bytes drift too much to model. The detector "
                             "passes them through unchecked instead of flagging them as unknown.")
    args = parser.parse_args()

    # ── Load ──────────────────────────────────────────────────────────────────
    # dtype=str: keep hex IDs like "60E" from being parsed as floats (60E -> 60.0)
    df = pd.read_csv(args.csv, dtype=str)

    # ── Validate: only normal traffic allowed ─────────────────────────────────
    if args.ignore_label:
        print("[INFO] --ignore-label set — assuming all rows are normal traffic.")
    elif "label" in df.columns:
        attack_rows = (pd.to_numeric(df["label"]) != 0).sum()
        if attack_rows > 0:
            print(
                f"[ERROR] The CSV contains {attack_rows} row(s) with label != 0 (attack data).\n"
                f"        Training requires a normal-traffic-only file (all labels must be 0).\n"
                f"        Please filter the CSV or use a capture that contains no attack traffic."
            )
            sys.exit(1)
    else:
        print("[WARNING] No 'label' column found — assuming all rows are normal traffic.")

    # ── Feature matrix ────────────────────────────────────────────────────────
    missing = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        print(
            f"[ERROR] The CSV is missing the following required columns: {missing}\n"
            f"        Re-run candump_csv_parser.py to generate an up-to-date CSV."
        )
        sys.exit(1)

    X = build_features(df)
    excluded_ids = [x.strip().upper() for x in args.exclude_ids.split(",") if x.strip()]
    X = X[~X["can_id"].isin([int(x, 16) for x in excluded_ids])]

    print(f"Training Isolation Forest on {len(X)} samples with features: {list(X.columns)}")
    if excluded_ids:
        print(f"Excluded CAN IDs: {excluded_ids}")

    # ── Train ─────────────────────────────────────────────────────────────────
    # Fit on numpy array (not DataFrame) so the model stores no feature names.
    # This avoids a UserWarning on every predict() call at inference time.
    model = IsolationForest(random_state=42)
    model.fit(X.values)

    # ── Per-ID thresholds ─────────────────────────────────────────────────────
    # One global cutoff can't be strict for single-byte control IDs (604#00 vs 604#01)
    # and loose for multi-byte ones at the same time, so each ID gets its own cutoff:
    # the lowest score any of its normal frames got. Anything scoring below it is
    # more anomalous than everything seen in training for that ID.
    scores = model.score_samples(X.values)
    can_ids = X["can_id"].values
    thresholds = {
        format(int(can_id), "X"): float(scores[can_ids == can_id].min()) - 1e-6
        for can_id in sorted(set(can_ids))
    }
    print(f"Per-ID score thresholds: { {k: round(v, 3) for k, v in thresholds.items()} }")

    # ── Save ──────────────────────────────────────────────────────────────────
    args.output_dir.mkdir(parents=True, exist_ok=True)

    dbc_stem = args.dbc.stem
    csv_stem = args.csv.stem
    output_path = args.output_dir / f"{dbc_stem}__{csv_stem}__{ALGORITHM}.pkl"

    joblib.dump({"model": model, "thresholds": thresholds, "excluded_ids": excluded_ids}, output_path)
    print(f"Model saved to: {output_path}")


if __name__ == "__main__":
    main()
