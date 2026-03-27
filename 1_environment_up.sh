#!/bin/bash

# Start CARLA simulator in the background
echo "Starting CARLA simulator..."
./carla/CarlaUE4.sh -RenderOffScreen -quality_level=Low -nosound &

# Set up virtual CAN bus
echo "Setting up virtual CAN bus..."
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0

echo "Environment is up!"
