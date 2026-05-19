#!/bin/bash
set -e

DBC_PATH="${DBC_PATH:-data/carla.dbc}"
VCAN_INTERFACE="${VCAN_INTERFACE:-vcan0}"
CARLA_HOST="${CARLA_HOST:-127.0.0.1}"
CARLA_PORT="${CARLA_PORT:-2000}"

echo "============================================"
echo "  Yes, CARLA CAN — Docker Platform"
echo "============================================"
echo "  DBC file  : ${DBC_PATH}"
echo "  vCAN      : ${VCAN_INTERFACE}"
echo "  CARLA host: ${CARLA_HOST}:${CARLA_PORT}"
echo "============================================"

# ──────────────────────────────────────────────────────────────────────
# Wait for vcan0 to be available (created by the vcan-setup service)
# ──────────────────────────────────────────────────────────────────────
echo "Waiting for ${VCAN_INTERFACE}..."
TIMEOUT=30
ELAPSED=0
while ! ip link show "${VCAN_INTERFACE}" 2>/dev/null | grep -q UP; do
    if [ $ELAPSED -ge $TIMEOUT ]; then
        echo "ERROR: ${VCAN_INTERFACE} did not come up within ${TIMEOUT}s."
        exit 1
    fi
    sleep 0.5
    ELAPSED=$((ELAPSED + 1))
done
echo "${VCAN_INTERFACE} is ready."

# ──────────────────────────────────────────────────────────────────────
# Wait for CARLA server to accept connections
# ──────────────────────────────────────────────────────────────────────
echo "Waiting for CARLA server at ${CARLA_HOST}:${CARLA_PORT}..."
TIMEOUT=60
ELAPSED=0
while ! python -c "import socket; s=socket.socket(); s.settimeout(1); s.connect(('${CARLA_HOST}', ${CARLA_PORT})); s.close()" 2>/dev/null; do
    if [ $ELAPSED -ge $TIMEOUT ]; then
        echo "ERROR: CARLA server did not respond within ${TIMEOUT}s."
        exit 1
    fi
    sleep 1
    ELAPSED=$((ELAPSED + 1))
done
echo "CARLA server is ready."

# ──────────────────────────────────────────────────────────────────────
# Start CARLA client module (background)
# ──────────────────────────────────────────────────────────────────────
echo "Starting CARLA client module..."
python CARLA_client_module.py \
    --host "${CARLA_HOST}" \
    --vcan "${VCAN_INTERFACE}" &
CLIENT_PID=$!

# Give the client a moment to connect and spawn the vehicle
sleep 3

# ──────────────────────────────────────────────────────────────────────
# Start vehicle controls module (background)
# ──────────────────────────────────────────────────────────────────────
echo "Starting vehicle controls module..."
python vehicle_controls_module.py \
    --dbc "${DBC_PATH}" \
    --vcan "${VCAN_INTERFACE}" &
CONTROLS_PID=$!

echo ""
echo "============================================"
echo "  Environment is up!"
echo "============================================"
echo ""
echo "  To run experiments in a separate terminal:"
echo "    docker compose exec platform python cyberattacks_module.py --feature hand_brake --period 0.001"
echo "    docker compose exec platform python intrusion_detection_module.py --detector id_time"
echo "    docker compose exec platform candump vcan0"
echo ""

# ──────────────────────────────────────────────────────────────────────
# Graceful shutdown handler
# ──────────────────────────────────────────────────────────────────────
cleanup() {
    echo ""
    echo "Shutting down platform modules..."
    kill $CONTROLS_PID 2>/dev/null || true
    kill $CLIENT_PID 2>/dev/null || true
    wait $CONTROLS_PID 2>/dev/null || true
    wait $CLIENT_PID 2>/dev/null || true
    echo "Platform modules stopped."
}
trap cleanup SIGTERM SIGINT

# Wait for either process to exit, then clean up
wait -n $CLIENT_PID $CONTROLS_PID 2>/dev/null || true
cleanup
