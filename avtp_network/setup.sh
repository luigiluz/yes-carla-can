#!/bin/bash
# =============================================================================
# setup.sh — Virtual AVTP Network: namespace + bridge setup
# =============================================================================
#
# Creates a minimal virtual Layer-2 network composed of three Linux network
# namespaces connected by a software bridge:
#
#   [sender ns]            [switch ns]            [receiver ns]
#   veth-s  ─────────── veth-s-sw   veth-r-sw ─────────── veth-r
#                           │            │
#                           └─── br0  ───┘
#
# No IP addresses are configured. AVTP operates at Ethernet (Layer 2) only.
#
# Usage:
#   sudo bash setup.sh              # bring up the virtual network
#   sudo bash setup.sh --capture    # bring up + start tcpdump on br0
#   sudo bash setup.sh --teardown   # destroy all namespaces / interfaces
#
# With --capture, all AVTP frames crossing the bridge are written to a
# timestamped .pcap file in the current directory.  The capture runs until
# --teardown is called or the process is killed manually.
#
# After setup, run each script inside its respective namespace, e.g.:
#   sudo ip netns exec receiver python3 receiver.py
#   sudo ip netns exec sender   python3 sender.py
#
# =============================================================================
set -euo pipefail

NS_SENDER="sender"
NS_SWITCH="switch"
NS_RECEIVER="receiver"

# ── Argument parsing ──────────────────────────────────────────────────────────
TEARDOWN=0
CAPTURE=0
for arg in "$@"; do
    case $arg in
        --teardown) TEARDOWN=1 ;;
        --capture)  CAPTURE=1  ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: $0 [--capture] [--teardown]"
            exit 1
            ;;
    esac
done

TCPDUMP_PID_FILE="/tmp/avtp_tcpdump.pid"

# ── Teardown ──────────────────────────────────────────────────────────────────
teardown() {
    echo "[*] Tearing down virtual AVTP network..."

    # Stop any running tcpdump capture.
    # tcpdump drops privileges to the 'tcpdump' user after opening the socket,
    # so a direct kill may be refused; deleting the namespace below will
    # terminate the process regardless.
    if [[ -f "$TCPDUMP_PID_FILE" ]]; then
        TDPID=$(cat "$TCPDUMP_PID_FILE")
        if kill -0 "$TDPID" 2>/dev/null; then
            kill "$TDPID" 2>/dev/null && echo "    stopped tcpdump (PID $TDPID)" || \
                echo "    tcpdump (PID $TDPID) will be stopped by namespace removal"
        fi
        rm -f "$TCPDUMP_PID_FILE"
    fi

    ip netns del "$NS_SENDER"   2>/dev/null && echo "    deleted namespace: $NS_SENDER"   || true
    ip netns del "$NS_SWITCH"   2>/dev/null && echo "    deleted namespace: $NS_SWITCH"   || true
    ip netns del "$NS_RECEIVER" 2>/dev/null && echo "    deleted namespace: $NS_RECEIVER" || true
    echo "[+] Teardown complete."
}

if [[ $TEARDOWN -eq 1 ]]; then
    teardown
    exit 0
fi

# ── Clean any leftover state ──────────────────────────────────────────────────
echo "[*] Cleaning up any previous namespaces..."
ip netns del "$NS_SENDER"   2>/dev/null || true
ip netns del "$NS_SWITCH"   2>/dev/null || true
ip netns del "$NS_RECEIVER" 2>/dev/null || true

# ── Create namespaces ─────────────────────────────────────────────────────────
echo "[*] Creating namespaces: $NS_SENDER, $NS_SWITCH, $NS_RECEIVER"
ip netns add "$NS_SENDER"
ip netns add "$NS_SWITCH"
ip netns add "$NS_RECEIVER"

# ── Create veth pairs ─────────────────────────────────────────────────────────
#   veth-s      <-> veth-s-sw    (sender side)
#   veth-r      <-> veth-r-sw    (receiver side)
echo "[*] Creating virtual Ethernet pairs..."
ip link add veth-s    type veth peer name veth-s-sw
ip link add veth-r    type veth peer name veth-r-sw

# ── Assign interfaces to namespaces ──────────────────────────────────────────
echo "[*] Moving interfaces into namespaces..."
ip link set veth-s    netns "$NS_SENDER"
ip link set veth-s-sw netns "$NS_SWITCH"
ip link set veth-r    netns "$NS_RECEIVER"
ip link set veth-r-sw netns "$NS_SWITCH"

# ── Bring up loopbacks ────────────────────────────────────────────────────────
ip -n "$NS_SENDER"   link set lo up
ip -n "$NS_SWITCH"   link set lo up
ip -n "$NS_RECEIVER" link set lo up

# ── Bring up veth endpoints ───────────────────────────────────────────────────
echo "[*] Bringing up interfaces..."
ip -n "$NS_SENDER"   link set veth-s    up
ip -n "$NS_RECEIVER" link set veth-r    up
ip -n "$NS_SWITCH"   link set veth-s-sw up
ip -n "$NS_SWITCH"   link set veth-r-sw up

# ── Create bridge in switch namespace ────────────────────────────────────────
echo "[*] Creating bridge br0 in $NS_SWITCH..."
ip -n "$NS_SWITCH" link add br0 type bridge
ip -n "$NS_SWITCH" link set br0 up

# Attach veth interfaces to the bridge
ip -n "$NS_SWITCH" link set veth-s-sw master br0
ip -n "$NS_SWITCH" link set veth-r-sw master br0

# Disable STP — we don't need spanning tree in this simple topology
ip -n "$NS_SWITCH" link set br0 type bridge stp_state 0

# ── Optional packet capture ───────────────────────────────────────────────────
CAP_FILE=""
if [[ $CAPTURE -eq 1 ]]; then
    CAP_FILE="avtp_capture_$(date +"%Y-%m-%d_%H:%M:%S").pcap"
    echo "[*] Starting packet capture → $CAP_FILE"
    ip netns exec "$NS_SWITCH" \
        tcpdump -i br0 -w "$(pwd)/$CAP_FILE" ether proto 0x22F0 \
        > /tmp/avtp_tcpdump.log 2>&1 &
    echo $! > "$TCPDUMP_PID_FILE"
    echo "    tcpdump PID: $(cat $TCPDUMP_PID_FILE)"
fi
# ── Summary ───────────────────────────────────────────────────────────────────
echo   ""
echo   "╔══════════════════════════════════════════════════════════════════╗"
echo   "║           Virtual AVTP Network — Ready                           ║"
echo   "╠══════════════════════════════════════════════════════════════════╣"
echo   "║  Topology                                                        ║"
echo   "║    [sender]─veth-s──veth-s-sw─┐                                  ║"
echo   "║                               br0  (switch ns)                   ║"
echo   "║  [receiver]─veth-r──veth-r-sw─┘                                  ║"
echo   "║                                                                  ║"
echo   "║  Layer 2 only — no IP addresses — EtherType 0x22F0 (AVTP)        ║"
echo   "╠══════════════════════════════════════════════════════════════════╣"
echo   "║  Activate the virtual environment first:                         ║"
echo   "║    source .venv/bin/activate                                     ║"
echo   "║                                                                  ║"
echo   "║  1. Start the receiver (in one terminal):                        ║"
echo   "║    sudo ip netns exec receiver python3 receiver.py               ║"
echo   "║                                                                  ║"
echo   "║  2. Start the sender (in another terminal):                      ║"
echo   "║    sudo ip netns exec sender python3 sender.py                   ║"
echo   "║                                                                  ║"
echo   "║  3. Inspect traffic at the switch (optional):                    ║"
echo   "║    sudo ip netns exec switch \                                   ║"
echo   "║      tcpdump -i br0 -e ether proto 0x22F0                        ║"
echo   "║                                                                  ║"
if [[ -n "$CAP_FILE" ]]; then
echo   "╠══════════════════════════════════════════════════════════════════╣"
echo   "║  Capture: ON                                                     ║"
printf "║  File   : %-55s║\n" "$CAP_FILE"
echo   "║  Stop   : sudo bash setup.sh --teardown  (kills tcpdump)         ║"
echo   "║  Open   : wireshark $CAP_FILE                                    ║"
echo   "║                                                                  ║"
fi      
echo   "║  Teardown:                                                       ║"
echo   "║    sudo bash setup.sh --teardown                                 ║"
echo   "╚══════════════════════════════════════════════════════════════════╝"