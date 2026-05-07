#!/bin/bash

CARLA_FOLDER_NAME="${CARLA_FOLDER_NAME:-carla-0-9-15}"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-n4s_env}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DBC_PATH="${DBC_PATH:-data/carla.dbc}"
VCAN_INTERFACE="${VCAN_INTERFACE:-vcan0}"

usage() {
    cat <<EOF
Usage: $0 [-h|--help] [--dbc <path>]

Start the "Yes, CARLA CAN" simulation environment.

What this script does:
  1. Launches the CARLA simulator in headless, low-quality mode
  2. Creates the virtual CAN bus (${VCAN_INTERFACE:-vcan0}) using the Linux kernel vcan module
  3. Waits 5 seconds for CARLA to initialise
  4. Starts the CARLA client module (spawns the vehicle and sensors)
  5. Starts the vehicle controls module (translates vehicle state into CAN frames)

Options:
  -h, --help      Show this help message and exit
  --dbc <path>    Path to the DBC file defining the virtual CAN network schema
                  (default: data/carla.dbc)
  --vcan <name>   Name of the virtual CAN interface to create (default: vcan0)

Environment variables:
  CARLA_FOLDER_NAME     Directory where CARLA is installed (default: carla-0-9-15)
  CONDA_ENV_NAME        Conda environment to use (default: n4s_env)
  DBC_PATH              DBC file path, overridden by --dbc if provided
  VCAN_INTERFACE        Virtual CAN interface name, overridden by --vcan if provided (default: vcan0)
  VK_ICD_FILENAMES      Force a specific Vulkan ICD file (skips auto-detection)
EOF
}

# Allow overriding the DBC file via --dbc argument
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --dbc) DBC_PATH="$2"; shift 2 ;;
        --vcan) VCAN_INTERFACE="$2"; shift 2 ;;
        *) echo "Unknown argument: $1"; usage; exit 1 ;;
    esac
done

# On hybrid Intel/NVIDIA systems, Vulkan may default to the Intel GPU and cause
# crashes. Force the NVIDIA ICD if available; otherwise fall back to the default.
# Skip auto-detection if the user already set VK_ICD_FILENAMES explicitly.
if [[ -n "${VK_ICD_FILENAMES}" ]]; then
    echo "VK_ICD_FILENAMES already set to '${VK_ICD_FILENAMES}'. Skipping auto-detection."
else
    NVIDIA_ICD=$(find /usr/share/vulkan/icd.d /etc/vulkan/icd.d 2>/dev/null -name "nvidia_icd*.json" | head -1)
    if [[ -n "${NVIDIA_ICD}" ]]; then
        echo "NVIDIA Vulkan ICD detected (${NVIDIA_ICD}). Forcing VK_ICD_FILENAMES to use NVIDIA GPU."
        export VK_ICD_FILENAMES="${NVIDIA_ICD}"
    else
        echo "No NVIDIA Vulkan ICD found. Using system default GPU."
    fi
fi

# Start CARLA simulator in the background
echo "Starting CARLA simulator..."
./${CARLA_FOLDER_NAME}/CarlaUE4.sh -RenderOffScreen -quality_level=Low -nosound 2>/dev/null &

# Set up virtual CAN bus
echo "Setting up virtual CAN bus..."
sudo modprobe vcan
sudo ip link add dev "${VCAN_INTERFACE}" type vcan
sudo ip link set up "${VCAN_INTERFACE}"

# Give CARLA a moment to initialise before connecting clients
echo "Waiting for CARLA to start..."
sleep 5

# Start CARLA client module in the background
echo "Starting CARLA client module..."
conda run -n "${CONDA_ENV_NAME}" python "${SCRIPT_DIR}/CARLA_client_module.py" --vcan "${VCAN_INTERFACE}" &

# Start vehicle controls module in the background
echo "Starting vehicle controls module..."
conda run -n "${CONDA_ENV_NAME}" python "${SCRIPT_DIR}/vehicle_controls_module.py" --dbc "${DBC_PATH}" --vcan "${VCAN_INTERFACE}" &

echo "Environment is up!"
