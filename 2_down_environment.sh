#!/bin/bash

usage() {
    cat <<EOF
Usage: $0 [-h|--help] [--can-mode virtual|physical]

Tear down the "Yes, CARLA CAN" simulation environment.

What this script does:
  1. Stops the vehicle controls module
  2. Stops the CARLA client module (waits up to 10 seconds for a clean exit)
  3. Stops the CARLA simulator
  4. In --can-mode virtual (default): removes the vxcan bridge (can-gw routes, vcan1) and
     the virtual CAN bus (vcan0), unloads the vcan/can-gw kernel modules
  5. In --can-mode physical: no CAN teardown needed (nothing was created)

Options:
  -h, --help           Show this help message and exit
  --can-mode <mode>    virtual or physical (default: virtual) — must match the mode used
                       with 1_up_environment.sh
EOF
}

CAN_MODE="${CAN_MODE:-virtual}"
VCAN_INTERFACE="${VCAN_INTERFACE:-vcan0}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --can-mode) CAN_MODE="$2"; shift 2 ;;
        *) echo "Unknown argument: $1"; usage; exit 1 ;;
    esac
done

# Stop vehicle controls module
echo "Stopping vehicle controls module..."
VEHICLE_CONTROLS_PID=$(pgrep -d ' ' -f "vehicle_controls_module.py")
if [ -n "$VEHICLE_CONTROLS_PID" ]; then
    kill $VEHICLE_CONTROLS_PID
    echo "vehicle_controls_module (PID $VEHICLE_CONTROLS_PID) stopped."
else
    echo "vehicle_controls_module process not found."
fi

# Stop CARLA client module and wait for it to exit so sensor streams are
# cleanly closed before the CARLA server is killed.
echo "Stopping CARLA client module..."
CARLA_CLIENT_PID=$(pgrep -d ' ' -f "CARLA_client_module.py")
if [ -n "$CARLA_CLIENT_PID" ]; then
    kill $CARLA_CLIENT_PID
    echo "Waiting for CARLA_client_module (PID $CARLA_CLIENT_PID) to exit..."
    TIMEOUT=10
    ELAPSED=0
    while kill -0 $CARLA_CLIENT_PID 2>/dev/null; do
        if [ $ELAPSED -ge $TIMEOUT ]; then
            echo "Timed out waiting; force-killing CARLA_client_module."
            kill -9 $CARLA_CLIENT_PID 2>/dev/null
            break
        fi
        sleep 0.2
        ELAPSED=$((ELAPSED + 1))
    done
    echo "CARLA_client_module (PID $CARLA_CLIENT_PID) stopped."
else
    echo "CARLA_client_module process not found."
fi

# Stop CARLA simulator only after the client has fully exited
echo "Stopping CARLA simulator..."
CARLA_PID=$(pgrep -d ' ' -f "CarlaUE4")
if [ -n "$CARLA_PID" ]; then
    kill $CARLA_PID
    echo "CARLA (PID $CARLA_PID) stopped."
else
    echo "CARLA process not found."
fi

if [[ "${CAN_MODE}" == "virtual" ]]; then
    # Bring virtual CAN bus down
    echo "Bringing virtual CAN bus down..."
    sudo cangw -D -s vcan1 -d "${VCAN_INTERFACE}" -e 2>/dev/null || true
    sudo cangw -D -s "${VCAN_INTERFACE}" -d vcan1 -e 2>/dev/null || true
    sudo ip link set down vcan1 2>/dev/null || true
    sudo ip link delete vcan1 2>/dev/null || true
    sudo ip link set down "${VCAN_INTERFACE}"
    sudo ip link delete "${VCAN_INTERFACE}"
    sudo modprobe -r can-gw 2>/dev/null || true
    sudo modprobe -r vcan
else
    echo "Physical CAN mode: nothing to tear down."
fi

echo "Environment is down!"
