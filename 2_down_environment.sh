#!/bin/bash

usage() {
    cat <<EOF
Usage: $0 [-h|--help]

Tear down the "Yes, CARLA CAN" simulation environment.

What this script does:
  1. Stops the vehicle controls module
  2. Stops the CARLA client module (waits up to 10 seconds for a clean exit)
  3. Stops the CARLA simulator
  4. Removes the vxcan bridge (can-gw routes, vcan1)
  5. Stops the CAN recorder (candump) of the current run
  6. Removes the virtual CAN bus (vcan0) and unloads the vcan/can-gw kernel modules
  7. Tears down the AVTP virtual network (and its packet capture), only if it exists

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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AVTP_DIR="${SCRIPT_DIR}/avtp_network"
VCAN_INTERFACE="${VCAN_INTERFACE:-vcan0}"
LOGS_DIR="${SCRIPT_DIR}/traffic_logs"

# AVTP is opt-in (1_up_environment.sh --avtp). Detect whether this run used it
# by checking for its network namespaces, so a run without AVTP is not touched.
if ip netns list 2>/dev/null | grep -qwE "sender|switch|receiver"; then
    AVTP_ACTIVE=1
else
    AVTP_ACTIVE=0
fi

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


if [ "$AVTP_ACTIVE" -eq 1 ]; then
    # Stop AVTP Receiver (caso esteja a rodar em background ou num terminal)
    echo "Stopping AVTP receiver..."
    RECEIVER_PID=$(pgrep -d ' ' -f "receiver.py")
    if [ -n "$RECEIVER_PID" ]; then
        kill $RECEIVER_PID 2>/dev/null || true
        echo "AVTP receiver (PID $RECEIVER_PID) stopped."
    else
        echo "AVTP receiver process not found."
    fi
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

# Stop the CAN recorder before removing the bus
echo "Stopping CAN recorder..."
if [ -f "${LOGS_DIR}/.candump.pid" ]; then
    CANDUMP_PID=$(cat "${LOGS_DIR}/.candump.pid")
    if kill "$CANDUMP_PID" 2>/dev/null; then
        echo "candump (PID $CANDUMP_PID) stopped."
    else
        echo "candump process not found."
    fi
    rm -f "${LOGS_DIR}/.candump.pid"
else
    echo "candump pid file not found."
fi

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


if [ "$AVTP_ACTIVE" -eq 1 ]; then
    # Limpa a rede virtual AVTP e o namespace
    echo "Tearing down AVTP virtual network..."
    if [ -f "${AVTP_DIR}/setup.sh" ]; then
        sudo bash "${AVTP_DIR}/setup.sh" --teardown
    else
        # Fallback caso o setup.sh não seja encontrado
        sudo ip netns delete sender 2>/dev/null || true
        sudo ip netns delete receiver 2>/dev/null || true
        sudo ip netns delete switch 2>/dev/null || true
    fi
fi

if [ -f "${LOGS_DIR}/.current_run" ]; then
    echo "Logs for this run: $(cat "${LOGS_DIR}/.current_run")"
fi
echo "Environment is down!"