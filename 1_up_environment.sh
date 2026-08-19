#!/bin/bash

CARLA_FOLDER_NAME="${CARLA_FOLDER_NAME:-carla-0-9-15}"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-n4s_env}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DBC_PATH="${DBC_PATH:-data/carla.dbc}"
CAN_MODE="${CAN_MODE:-virtual}"
VCAN_INTERFACE="${VCAN_INTERFACE:-vcan0}"
CLIENT_CAN_CHANNEL="${CLIENT_CAN_CHANNEL:-HSCAN}"
CLIENT_CAN_SERIAL="${CLIENT_CAN_SERIAL:-}"
CONTROLS_CAN_CHANNEL="${CONTROLS_CAN_CHANNEL:-HSCAN}"
CONTROLS_CAN_SERIAL="${CONTROLS_CAN_SERIAL:-}"
CAN_BITRATE="${CAN_BITRATE:-}"

usage() {
    cat <<EOF
Usage: $0 [-h|--help] [--dbc <path>] [--can-mode virtual|physical] [...]

Start the "Yes, CARLA CAN" simulation environment.

What this script does:
  1. Launches the CARLA simulator in headless, low-quality mode
  2. Sets up the CAN bus (virtual by default, or physical Intrepid hardware with --can-mode physical)
  3. Waits 5 seconds for CARLA to initialise
  4. Starts the CARLA client module (spawns the vehicle and sensors)
  5. Starts the vehicle controls module (translates vehicle state into CAN frames)

In --can-mode virtual (default):
  Creates the virtual CAN bus (${VCAN_INTERFACE}) using the Linux kernel vcan module, plus
  a second virtual CAN bus (vcan1) for the attacker, bridged via can-gw so that candump
  labels attacker frames as 'R' and normal frames as 'T'. Both node scripts share it.

In --can-mode physical:
  Skips all vcan/can-gw setup. Each node script talks to its own Intrepid CAN device,
  selected by serial number — the CARLA client module and the vehicle controls module are
  independent processes and may be wired to two different physical devices. Requires
  --client-can-serial and --controls-can-serial. Note: the attacker/IDS demo path
  (cyberattacks_module.py, intrusion_detection_module.py) relies on the vcan1/can-gw bridge
  and stays virtual-only for now.

Options:
  -h, --help                  Show this help message and exit
  --dbc <path>                Path to the DBC file defining the CAN network schema
                               (default: data/carla.dbc)
  --can-mode <mode>           virtual or physical (default: virtual)
  --vcan <name>                [virtual mode] Name of the virtual CAN interface to create
                               (default: vcan0)
  --client-can-serial <SN>    [physical mode] Serial of the device for CARLA_client_module.py
  --client-can-channel <name> [physical mode] Channel/NetID for that device (default: HSCAN)
  --controls-can-serial <SN>  [physical mode] Serial of the device for vehicle_controls_module.py
  --controls-can-channel <name> [physical mode] Channel/NetID for that device (default: HSCAN)
  --can-bitrate <bps>         [physical mode] Bus bitrate (default: auto-detect)

Environment variables:
  CARLA_FOLDER_NAME     Directory where CARLA is installed (default: carla-0-9-15)
  CONDA_ENV_NAME        Conda environment to use (default: n4s_env)
  DBC_PATH              DBC file path, overridden by --dbc if provided
  CAN_MODE              virtual or physical, overridden by --can-mode if provided
  VCAN_INTERFACE        Virtual CAN interface name, overridden by --vcan if provided
  VK_ICD_FILENAMES      Force a specific Vulkan ICD file (skips auto-detection)
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --dbc) DBC_PATH="$2"; shift 2 ;;
        --can-mode) CAN_MODE="$2"; shift 2 ;;
        --vcan) VCAN_INTERFACE="$2"; shift 2 ;;
        --client-can-serial) CLIENT_CAN_SERIAL="$2"; shift 2 ;;
        --client-can-channel) CLIENT_CAN_CHANNEL="$2"; shift 2 ;;
        --controls-can-serial) CONTROLS_CAN_SERIAL="$2"; shift 2 ;;
        --controls-can-channel) CONTROLS_CAN_CHANNEL="$2"; shift 2 ;;
        --can-bitrate) CAN_BITRATE="$2"; shift 2 ;;
        *) echo "Unknown argument: $1"; usage; exit 1 ;;
    esac
done

if [[ "${CAN_MODE}" != "virtual" && "${CAN_MODE}" != "physical" ]]; then
    echo "Invalid --can-mode '${CAN_MODE}' (expected 'virtual' or 'physical')"
    exit 1
fi

if [[ "${CAN_MODE}" == "physical" ]]; then
    if [[ -z "${CLIENT_CAN_SERIAL}" || -z "${CONTROLS_CAN_SERIAL}" ]]; then
        echo "--can-mode physical requires both --client-can-serial and --controls-can-serial"
        echo "(each node script opens its own device; the serial can't be guessed with more than one attached)"
        exit 1
    fi
    if [[ -z "${CAN_BITRATE}" ]]; then
        echo "WARNING: --can-mode physical without --can-bitrate relies on auto-bitrate"
        echo "detection, which needs to observe existing traffic to lock onto a rate and"
        echo "can fail to lock (frames then hang trying to transmit) on a quiet bus. Pass"
        echo "--can-bitrate explicitly (e.g. 500000 for a typical vehicle HS-CAN bus) if"
        echo "sends hang or devices fail to come up."
    fi
fi

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

CLIENT_ARGS=()
CONTROLS_ARGS=(--dbc "${DBC_PATH}")

if [[ "${CAN_MODE}" == "virtual" ]]; then
    echo "Setting up virtual CAN bus..."
    sudo modprobe vcan
    sudo modprobe can-gw
    sudo ip link add dev "${VCAN_INTERFACE}" type vcan
    sudo ip link set up "${VCAN_INTERFACE}"

    # Set up attacker CAN bus and bridge it to the main bus via can-gw.
    # Frames sent on vcan1 are forwarded to vcan0 and marked 'R' (received) by candump,
    # while frames sent directly on vcan0 are marked 'T' (transmitted).
    echo "Setting up attacker CAN bus and can-gw bridge..."
    sudo ip link add dev vcan1 type vcan
    sudo ip link set up vcan1
    sudo cangw -A -s vcan1 -d "${VCAN_INTERFACE}" -e
    sudo cangw -A -s "${VCAN_INTERFACE}" -d vcan1 -e

    export CAN_INTERFACE="socketcan"
    CLIENT_ARGS+=(--vcan "${VCAN_INTERFACE}")
    CONTROLS_ARGS+=(--vcan "${VCAN_INTERFACE}")
else
    echo "Physical CAN mode: skipping vcan/can-gw setup."
    export CAN_INTERFACE="neovi"
    [[ -n "${CAN_BITRATE}" ]] && export CAN_BITRATE
    CLIENT_ARGS+=(--vcan "${CLIENT_CAN_CHANNEL}" --can-serial "${CLIENT_CAN_SERIAL}")
    CONTROLS_ARGS+=(--vcan "${CONTROLS_CAN_CHANNEL}" --can-serial "${CONTROLS_CAN_SERIAL}")
fi

# Give CARLA a moment to initialise before connecting clients
echo "Waiting for CARLA to start..."
sleep 5

# Start CARLA client module in the background
echo "Starting CARLA client module..."
conda run -n "${CONDA_ENV_NAME}" python "${SCRIPT_DIR}/CARLA_client_module.py" "${CLIENT_ARGS[@]}" &

# Start vehicle controls module in the background
echo "Starting vehicle controls module..."
conda run -n "${CONDA_ENV_NAME}" python "${SCRIPT_DIR}/vehicle_controls_module.py" "${CONTROLS_ARGS[@]}" &

echo "Environment is up!"
