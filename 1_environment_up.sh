#!/bin/bash

CARLA_FOLDER_NAME="${CARLA_FOLDER_NAME:-carla-0-9-15}"

# Start CARLA simulator in the background
echo "Starting CARLA simulator..."
./${CARLA_FOLDER_NAME}/CarlaUE4.sh -RenderOffScreen -quality_level=Low -nosound &

# Set up virtual CAN bus
echo "Setting up virtual CAN bus..."
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0

echo "Environment is up!"
