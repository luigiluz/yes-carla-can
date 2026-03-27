#!/bin/bash

CARLA_FOLDER_NAME="${CARLA_FOLDER_NAME:-carla-0-9-15}"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-n4s_env}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Start CARLA simulator in the background
echo "Starting CARLA simulator..."
./${CARLA_FOLDER_NAME}/CarlaUE4.sh -RenderOffScreen -quality_level=Low -nosound &

# Set up virtual CAN bus
echo "Setting up virtual CAN bus..."
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0

# Give CARLA a moment to initialise before connecting clients
echo "Waiting for CARLA to start..."
sleep 5

# Start CARLA client module in the background
echo "Starting CARLA client module..."
conda run -n "${CONDA_ENV_NAME}" python "${SCRIPT_DIR}/CARLA_client_module.py" &

# Start vehicle controls module in the background
echo "Starting vehicle controls module..."
conda run -n "${CONDA_ENV_NAME}" python "${SCRIPT_DIR}/vehicle_controls_module.py" &

echo "Environment is up!"
