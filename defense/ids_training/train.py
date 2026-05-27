import argparse
import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest

ALGORITHM = "isolation_forest"
FEATURE_COLS = ["can_id"] + [f"payload_byte_{i}" for i in range(8)]
OUTPUT_DIR = Path(__file__).parent / "models"


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Convert hex string columns to integers suitable for model input."""
    X = pd.DataFrame()
    X["can_id"] = df["can_id"].apply(lambda x: int(str(x), 16))
    for col in [f"payload_byte_{i}" for i in range(8)]:
        X[col] = df[col].apply(lambda x: int(str(x), 16) if pd.notna(x) else 0)
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
    args = parser.parse_args()

    # ── Load ──────────────────────────────────────────────────────────────────
    df = pd.read_csv(args.csv)

    # ── Validate: only normal traffic allowed ─────────────────────────────────
    if "label" in df.columns:
        attack_rows = (df["label"] != 0).sum()
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

    print(f"Training Isolation Forest on {len(X)} samples with features: {list(X.columns)}")

    # ── Train ─────────────────────────────────────────────────────────────────
    model = IsolationForest(random_state=42)
    model.fit(X)

    # ── Save ──────────────────────────────────────────────────────────────────
    args.output_dir.mkdir(parents=True, exist_ok=True)

    dbc_stem = args.dbc.stem
    csv_stem = args.csv.stem
    output_path = args.output_dir / f"{dbc_stem}__{csv_stem}__{ALGORITHM}.pkl"

    joblib.dump(model, output_path)
    print(f"Model saved to: {output_path}")


if __name__ == "__main__":
    main()
