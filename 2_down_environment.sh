#!/bin/bash

usage() {
    cat <<EOF
Usage: $0 [-h|--help]

Tear down the "Yes, CARLA CAN" simulation environment.

What this script does:
  1. Stops the vehicle controls module
  2. Stops the CARLA client module (waits up to 10 seconds for a clean exit)
  3. Stops the CARLA simulator
  4. Removes the virtual CAN bus (vcan0) and unloads the vcan kernel module

Options:
  -h, --help    Show this help message and exit
EOF
}

for arg in "$@"; do
    case "$arg" in
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown argument: $arg"; usage; exit 1 ;;
    esac
done

VCAN_INTERFACE="${VCAN_INTERFACE:-vcan0}"

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

# Bring virtual CAN bus down
echo "Bringing virtual CAN bus down..."
sudo ip link set down "${VCAN_INTERFACE}"
sudo ip link delete "${VCAN_INTERFACE}"
sudo modprobe -r vcan

echo "Environment is down!"
