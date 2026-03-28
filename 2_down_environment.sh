#!/bin/bash

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
sudo ip link set down vcan0
sudo ip link delete vcan0
sudo modprobe -r vcan

echo "Environment is down!"
