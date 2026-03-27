#!/bin/bash

# Stop CARLA simulator
echo "Stopping CARLA simulator..."
CARLA_PID=$(pgrep -f "CarlaUE4")
if [ -n "$CARLA_PID" ]; then
    kill "$CARLA_PID"
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
