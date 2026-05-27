#!/usr/bin/env python3
"""Collect CAN traffic logs with candump for a fixed duration."""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect CAN traffic logs using candump for a fixed amount of time."
    )
    parser.add_argument(
        "-d",
        "--duration",
        type=float,
        required=True,
        help="Collection time in seconds.",
    )
    parser.add_argument(
        "-f",
        "--filename",
        default=None,
        help="Optional output log filename. If omitted, candump auto-generates a name.",
    )
    parser.add_argument(
        "--interface",
        default="vcan0",
        help="CAN interface to capture from (default: vcan0).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.duration <= 0:
        print("Error: duration must be greater than 0 seconds.", file=sys.stderr)
        return 1

    if shutil.which("candump") is None:
        print("Error: 'candump' command not found. Install can-utils.", file=sys.stderr)
        return 1

    logs_dir = Path("traffic_logs")
    logs_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "candump",
        args.interface,
        "-l",
        "-x",
    ]

    output_hint = "traffic_logs/candump-YYYY-MM-DD_HHMMSS.log"
    if args.filename:
        output_name = Path(args.filename).name
        cmd.extend(["-f", output_name])
        output_hint = str(logs_dir / output_name)

    print(
        f"Collecting CAN traffic on '{args.interface}' for {args.duration} seconds -> {output_hint}"
    )

    process = subprocess.Popen(cmd, cwd=str(logs_dir))
    try:
        process.wait(timeout=args.duration)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
        print("Collection interrupted by user.")
        return 130

    print("Collection finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
