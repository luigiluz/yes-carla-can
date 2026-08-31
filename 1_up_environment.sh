#!/bin/bash

CARLA_FOLDER_NAME="${CARLA_FOLDER_NAME:-carla-0-9-15}"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-n4s_env}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DBC_PATH="${DBC_PATH:-data/carla.dbc}"
VCAN_INTERFACE="${VCAN_INTERFACE:-vcan0}"
AVTP_DIR="/home/ju/virtual-avtp-network"

usage() {
    cat <<EOF
Usage: $0 [-h|--help] [--dbc <path>]

Start the "Yes, CARLA CAN" simulation environment.

What this script does:
  1. Launches the CARLA simulator in headless, low-quality mode
  2. Creates the virtual CAN bus (${VCAN_INTERFACE:-vcan0}) using the Linux kernel vcan module
  3. Creates a second virtual CAN bus (vcan1) for the attacker and bridges them via can-gw
     so that candump labels attacker frames as 'R' and normal frames as 'T'
  4. Waits 5 seconds for CARLA to initialise
  5. Starts the CARLA client module (spawns the vehicle and sensors)
  6. Starts the vehicle controls module (translates vehicle state into CAN frames)

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



# Resolve Conda Python binary dynamically (no hardcoded user paths)
if [[ -n "${CONDA_PREFIX}" && "${CONDA_DEFAULT_ENV}" == "${CONDA_ENV_NAME}" ]]; then
    PYTHON_EXEC="${CONDA_PREFIX}/bin/python"
else
    # Fallback search via conda environment list
    PYTHON_EXEC=$(conda env list 2>/dev/null | grep -E "^${CONDA_ENV_NAME}[[:space:]]" | awk '{print $NF"/bin/python"}')
fi

# Fallback to system python if Conda is not active or environment not found
if [[ -z "${PYTHON_EXEC}" || ! -f "${PYTHON_EXEC}" ]]; then
    PYTHON_EXEC=$(which python)
fi

echo "Using Python binary: ${PYTHON_EXEC}"



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
./${CARLA_FOLDER_NAME}/CarlaUE4.sh -RenderOffScreen -quality-level=Low -nosound 2>/dev/null &

echo "Setting up AVTP virtual network..."
sudo bash -c "source ${AVTP_DIR}/.venv/bin/activate && bash ${AVTP_DIR}/setup.sh --capture"


echo "Connecting AVTP veth-s to Host..."
sudo ip netns exec sender ip link set veth-s netns 1 2>/dev/null || true
sudo ip link set dev veth-s up



# Set up virtual CAN bus
echo "Setting up virtual CAN bus..."
sudo modprobe vcan
sudo modprobe can-gw
sudo ip link add dev "${VCAN_INTERFACE}" type vcan 2>/dev/null || true
sudo ip link set up "${VCAN_INTERFACE}"

# Set up attacker CAN bus and bridge it to the main bus via can-gw.
# Frames sent on vcan1 are forwarded to vcan0 and marked 'R' (received) by candump,
# while frames sent directly on vcan0 are marked 'T' (transmitted).
echo "Setting up attacker CAN bus and can-gw bridge..."
sudo ip link add dev vcan1 type vcan
sudo ip link set up vcan1
sudo cangw -A -s vcan1 -d "${VCAN_INTERFACE}" -e 2>/dev/null || true
sudo cangw -A -s "${VCAN_INTERFACE}" -d vcan1 -e 2>/dev/null || true



# Give CARLA a moment to initialise before connecting clients
echo "Waiting for CARLA to start..."
sleep 5

# Executa os módulos Python no Host com privilégios para o Scapy
echo "Starting CARLA client module..."
sudo "${PYTHON_EXEC}" "${SCRIPT_DIR}/CARLA_client_module.py" --vcan "${VCAN_INTERFACE}" &

echo "Starting vehicle controls module..."
sudo "${PYTHON_EXEC}" "${SCRIPT_DIR}/vehicle_controls_module.py" --dbc "${DBC_PATH}" --vcan "${VCAN_INTERFACE}" &

echo "Environment is up!"