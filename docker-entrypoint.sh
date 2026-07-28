#!/bin/bash
set -Eeuo pipefail

DBC_PATH="${DBC_PATH:-data/carla.dbc}"
VCAN_INTERFACE="${VCAN_INTERFACE:-vcan0}"
VCAN_ATTACKER_INTERFACE="${VCAN_ATTACKER_INTERFACE:-vcan1}"
CARLA_HOST="${CARLA_HOST:-127.0.0.1}"
CARLA_PORT="${CARLA_PORT:-2000}"

CLIENT_PID=""
AUTOPILOT_PID=""
CONTROLS_PID=""
CLEANED_UP=0
OWNED_INTERFACES=()

if [[ "${VCAN_INTERFACE}" == "${VCAN_ATTACKER_INTERFACE}" ]]; then
    echo "ERROR: VCAN_INTERFACE and VCAN_ATTACKER_INTERFACE must be different." >&2
    exit 1
fi

remove_routes() {
    cangw -D -s "${VCAN_ATTACKER_INTERFACE}" -d "${VCAN_INTERFACE}" -e 2>/dev/null || true
    cangw -D -s "${VCAN_INTERFACE}" -d "${VCAN_ATTACKER_INTERFACE}" -e 2>/dev/null || true
}

cleanup() {
    if (( CLEANED_UP )); then
        return
    fi
    CLEANED_UP=1
    trap - EXIT TERM INT
    set +e

    echo "Shutting down client processes and virtual CAN interfaces..."
    [[ -z "${CONTROLS_PID}" ]] || kill "${CONTROLS_PID}" 2>/dev/null || true
    [[ -z "${AUTOPILOT_PID}" ]] || kill "${AUTOPILOT_PID}" 2>/dev/null || true
    [[ -z "${CLIENT_PID}" ]] || kill "${CLIENT_PID}" 2>/dev/null || true
    [[ -z "${CONTROLS_PID}" ]] || wait "${CONTROLS_PID}" 2>/dev/null || true
    [[ -z "${AUTOPILOT_PID}" ]] || wait "${AUTOPILOT_PID}" 2>/dev/null || true
    [[ -z "${CLIENT_PID}" ]] || wait "${CLIENT_PID}" 2>/dev/null || true

    remove_routes
    for ((index = ${#OWNED_INTERFACES[@]} - 1; index >= 0; index--)); do
        ip link delete dev "${OWNED_INTERFACES[index]}" 2>/dev/null || true
    done
    echo "Client cleanup complete."
}

ensure_vcan_interface() {
    local interface="$1"

    if ip link show dev "${interface}" >/dev/null 2>&1; then
        if ! ip -details link show dev "${interface}" | grep -Eq '(^|[[:space:]])vcan([[:space:]]|$)'; then
            echo "ERROR: Existing interface '${interface}' is not a vCAN interface." >&2
            return 1
        fi
        echo "Reusing existing vCAN interface ${interface}."
    else
        ip link add dev "${interface}" type vcan
        echo "Created vCAN interface ${interface}."
    fi

    OWNED_INTERFACES+=("${interface}")
    ip link set dev "${interface}" up
}

trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

if [[ -z "${DISPLAY:-}" ]]; then
    echo "ERROR: DISPLAY is not set. Start Compose from a terminal in your graphical session." >&2
    exit 1
fi

if [[ -z "${XAUTHORITY:-}" || ! -r "${XAUTHORITY}" ]]; then
    echo "ERROR: XAUTHORITY does not point to a readable file inside the client container." >&2
    exit 1
fi

echo "Checking X11 access at ${DISPLAY}..."
if ! python -c 'import tkinter as tk; root = tk.Tk(); root.withdraw(); root.update_idletasks(); root.destroy()'; then
    echo "ERROR: The client cannot authenticate with X11 at ${DISPLAY}." >&2
    echo "Start Compose as your desktop user and ensure the host XAUTHORITY path is correct." >&2
    exit 1
fi

echo "Loading virtual CAN kernel modules..."
modprobe vcan
modprobe can-gw
ensure_vcan_interface "${VCAN_INTERFACE}"
ensure_vcan_interface "${VCAN_ATTACKER_INTERFACE}"
remove_routes
cangw -A -s "${VCAN_ATTACKER_INTERFACE}" -d "${VCAN_INTERFACE}" -e
cangw -A -s "${VCAN_INTERFACE}" -d "${VCAN_ATTACKER_INTERFACE}" -e
echo "${VCAN_INTERFACE} and ${VCAN_ATTACKER_INTERFACE} are UP and bridged."

echo "Waiting for CARLA at ${CARLA_HOST}:${CARLA_PORT}..."
TIMEOUT=60
STARTED_AT=${SECONDS}
while ! python -c 'import socket, sys; socket.create_connection((sys.argv[1], int(sys.argv[2])), 1).close()' \
    "${CARLA_HOST}" "${CARLA_PORT}" 2>/dev/null; do
    if (( SECONDS - STARTED_AT >= TIMEOUT )); then
        echo "ERROR: CARLA did not respond within ${TIMEOUT}s." >&2
        exit 1
    fi
    sleep 1
done

echo "Starting CARLA client module..."
python CARLA_client_module.py \
    --host "${CARLA_HOST}" \
    --port "${CARLA_PORT}" \
    --vcan "${VCAN_INTERFACE}" &
CLIENT_PID=$!

sleep 3
if ! kill -0 "${CLIENT_PID}" 2>/dev/null; then
    if wait "${CLIENT_PID}"; then
        CLIENT_STATUS=1
    else
        CLIENT_STATUS=$?
    fi
    echo "ERROR: CARLA client exited during startup (status ${CLIENT_STATUS})." >&2
    exit "${CLIENT_STATUS}"
fi

echo "Starting CAN autopilot module..."
python autopilot_module.py \
    --host "${CARLA_HOST}" \
    --port "${CARLA_PORT}" \
    --dbc "${DBC_PATH}" \
    --vcan "${VCAN_INTERFACE}" &
AUTOPILOT_PID=$!

echo "Starting vehicle controls module..."
python vehicle_controls_module.py \
    --dbc "${DBC_PATH}" \
    --vcan "${VCAN_INTERFACE}" &
CONTROLS_PID=$!

echo "Environment is up. From the repository directory, run experiments in another terminal:"
echo "  docker compose exec client python cyberattacks_module.py --feature hand_brake --vcan ${VCAN_ATTACKER_INTERFACE}"
echo "  docker compose exec client python intrusion_detection_module.py --detector id_time --vcan ${VCAN_INTERFACE}"
echo "  docker compose exec client candump ${VCAN_INTERFACE}"

if wait -n "${CLIENT_PID}" "${AUTOPILOT_PID}" "${CONTROLS_PID}"; then
    CHILD_STATUS=0
else
    CHILD_STATUS=$?
fi

echo "A client process exited (status ${CHILD_STATUS}); stopping the other processes."
exit "${CHILD_STATUS}"
