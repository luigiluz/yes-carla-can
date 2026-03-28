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

# Stop CARLA client module
echo "Stopping CARLA client module..."
CARLA_CLIENT_PID=$(pgrep -d ' ' -f "CARLA_client_module.py")
if [ -n "$CARLA_CLIENT_PID" ]; then
    kill $CARLA_CLIENT_PID
    echo "CARLA_client_module (PID $CARLA_CLIENT_PID) stopped."
else
    echo "CARLA_client_module process not found."
fi

# Stop CARLA simulator
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
