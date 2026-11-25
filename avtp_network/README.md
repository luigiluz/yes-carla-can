# AVTP camera network

This folder adds an **automotive Ethernet camera link** to Yes, CARLA CAN. The
hood camera of the CARLA ego vehicle is encoded as H.264 video, packed into
**AVTP (IEEE 1722) IEC 61883-4 MPEG-TS** packets and sent over a virtual
Layer-2 network built from Linux network namespaces. On the other side, the
**vehicle controls module** receives the stream, shows it live and hands it to
a **decision engine**, completing the pipeline:

```
camera ──AVTP──► [decision engine] ──► vehicle controls ──CAN──► vehicle
```

The AVTP network is **opt-in**: it is only created when the environment is
started with `--avtp`.

---

## Table of Contents

1. [Quick start](#quick-start)
2. [Architecture](#architecture)
3. [Packet format](#packet-format)
4. [Files](#files)
5. [Logs and captures](#logs-and-captures)
6. [Running the receiver standalone](#running-the-receiver-standalone)
7. [Inspecting the traffic](#inspecting-the-traffic)

---

## Quick start

```bash
./1_up_environment.sh --avtp
```

This brings up CARLA, the CAN bus **and** the AVTP network. Once the windows
appear:

- the **ffplay** window ("AVTP Live Stream") shows the hood camera as received
  over AVTP;
- the vehicle controls window shows `AVTP rx: <packets> | <KB> | loss <n>`
  in its top-left corner;
- in the CARLA client window, `M` pauses/resumes the camera stream.

Tear everything down with:

```bash
./2_down_environment.sh
```

If the ffplay window does not open, allow root processes to use your X display
with `xhost +local:root` and start again.

---

## Architecture

```
          host (root namespace)                switch (ns)               host (root namespace)
 ┌────────────────────────────────┐      ┌──────────────────────┐      ┌─────────────────────────────────────┐
 │ CARLA_client_module.py         │      │   Linux bridge br0   │      │ vehicle_controls_module.py          │
 │  sensors/camera.py             │      │   (no IP, no STP)    │      │  AvtpReceiver (thread)              │
 │   CARLA RGB camera 960x400     │      │                      │      │   ├─► ffplay (live window)          │
 │   → H.264 / MPEG-TS (PyAV)     │      │  ┌──────────┐        │      │   ├─► avtp_stream.ts (run folder)   │
 │   → AVTP packets (raw socket)  │      │  │veth-s-sw │        │      │   └─► DecisionEngine.on_ts_data()   │
 │                                │      │  └────┬─────┘        │      │  DecisionEngine.apply(control)      │
 │          veth-s ───────────────┼──────┼──────►│ br0          │      │   → CAN frames on vcan0             │
 │                                │      │  ┌────┴─────┐        │      │                                     │
 │                                │      │  │veth-r-sw │────────┼──────┼──────► veth-r                       │
 │                                │      │  └──────────┘        │      │                                     │
 └────────────────────────────────┘      │  tcpdump → avtp.pcap │      └─────────────────────────────────────┘
                                         └──────────────────────┘

 EtherType 0x22F0 (AVTP) · pure Layer 2 · no IP addresses
```

How the network is built:

1. `setup.sh` creates three namespaces (`sender`, `switch`, `receiver`) and two
   veth pairs (virtual patch cables): `veth-s ↔ veth-s-sw` and
   `veth-r ↔ veth-r-sw`. The `-sw` ends are attached to bridge `br0` inside
   `switch`, which forwards Ethernet frames like a physical switch.
2. `1_up_environment.sh --avtp` then moves **both** outer ends, `veth-s` and
   `veth-r`, into the host namespace. The CARLA client (sender) and the vehicle
   controls (receiver) run on the host, so they can reach `vcan0`, the CARLA
   server on localhost and their AVTP interface at the same time. Frames still
   travel through `br0` in the `switch` namespace.
3. With `--capture`, `tcpdump` records every AVTP frame crossing `br0`.

### Sender: `sensors/camera.py`

`RGBCameraSensor` (created only when the client runs with `--avtp`):

1. receives each 960x400 camera image from CARLA at 30 FPS;
2. encodes it with `MPEGTSStreamEncoder` (PyAV / FFmpeg, H.264, `zerolatency`,
   a keyframe every 5 frames, SPS/PPS repeated) into MPEG-TS;
3. prefixes every 188-byte TS packet with a 4-byte source packet header (SPH),
   giving 192-byte blocks (IEC 61883-4);
4. calls `avtp.fragment_mpegts_stream()` to pack 2 blocks per AVTP packet and
   sends them on `veth-s` through a raw `AF_PACKET` socket.

### Receiver: `receiver.py` inside `vehicle_controls_module.py`

`AvtpReceiver` opens a raw socket bound to EtherType `0x22F0` on `veth-r`
(16 MB kernel receive buffer) and runs the receive loop in a background thread.
For every packet `ReceiverState.handle_packet()`:

1. extracts the TS packets with `avtp.parse_mpegts_stream_packet()`;
2. checks the AVTP `sequence_num` and counts lost packets;
3. writes the TS data to `avtp_stream.ts`;
4. passes it to the `on_ts_data` callback (the decision engine);
5. feeds ffplay through a pipe, after an initial 3264-byte de-jitter buffer.

`stop()` closes the socket, the file and ffplay, and prints a reception
summary. The vehicle controls module calls it on ESC, Ctrl-C and SIGTERM
(`2_down_environment.sh`).

### Decision engine: `decision_engine.py`

`DecisionEngine` sits between the stream and the CAN output. Every control
produced by the keyboard passes through `DecisionEngine.apply(control)` before
it is sent on the CAN bus. It is currently a **pass-through stub**: it records
the incoming video data and returns the control unchanged. Perception and
decision logic (e.g. decoding frames and adjusting throttle/brake/steer) goes
there.

---

## Packet format

Every AVTP frame is 430 bytes:

```
┌───────────┬──────────────────────┬──────────┬───────────────────┬───────────────────┐
│ Ethernet  │ AVTP 61883 header    │ CIP      │ block 1           │ block 2           │
│ 14 B      │ 24 B                 │ 8 B      │ SPH 4 B + TS 188 B│ SPH 4 B + TS 188 B│
└───────────┴──────────────────────┴──────────┴───────────────────┴───────────────────┘
 offset 0     14                     38         46 (TS sync 0x47 at 50)
```

| Field | Value |
|---|---|
| Destination MAC | `91:e0:f0:00:fe:00` (AVTP multicast, IEEE 1722 Annex B) |
| EtherType | `0x22F0` |
| AVTP subtype | `0x00` (IEC 61883/IIDC) |
| `sequence_num` | byte 16; increments per packet, wraps at 255 (used for loss detection) |
| `stream_id` | `0xAABBCCDDEEFF0001` (default) |
| `stream_data_length` | `0x0188` = 392 B (CIP + 2 blocks) |
| 1394 tag/channel, tcode | `0x5F`, `0xA0` |
| CIP header | `3F 06 C4 <DBC> A0 00 00 00`; FMT = MPEG-TS, DBC increases by 16 per packet |

The last packet of an encoded frame is padded with null TS packets
(PID `0x1FFF`) when needed.

---

## Files

| File | Purpose |
|---|---|
| `setup.sh` | Create/tear down the namespaces, veth pairs and bridge; optional tcpdump capture |
| `avtp.py` | Build (`fragment_mpegts_stream`) and parse (`parse_mpegts_stream_packet`) AVTP MPEG-TS packets |
| `receiver.py` | `AvtpReceiver` / `ReceiverState`, also usable as a standalone script |
| `../sensors/camera.py` | Camera sensor, H.264/MPEG-TS encoder and AVTP sender |
| `../decision_engine.py` | Decision engine stub between the stream and the vehicle controls |

### `setup.sh`

```
sudo bash setup.sh [--capture [--capture-dir <dir>]] [--teardown]
```

| Flag | Description |
|---|---|
| *(none)* | Create namespaces, veth pairs and bridge |
| `--capture` | Also start `tcpdump` on `br0` |
| `--capture-dir <dir>` | Write `<dir>/avtp.pcap` and `<dir>/tcpdump.log` (without it: `./avtp_capture_<timestamp>.pcap`) |
| `--teardown` | Stop the capture and delete all namespaces (this also removes `veth-s`/`veth-r` from the host) |

You normally do not call it directly: `1_up_environment.sh --avtp` and
`2_down_environment.sh` do.

### AVTP options of the modules

| Module | Option | Description |
|---|---|---|
| `CARLA_client_module.py` | `--avtp` | Create the camera sensor and stream it on `veth-s` |
| `vehicle_controls_module.py` | `--avtp` | Start the receiver and the decision engine |
| | `--avtp-interface` | Interface to listen on (default `veth-r`) |
| | `--log-dir` | Folder for `avtp_stream.ts` (`1_up` passes the run folder) |
| | `--no-video-window` | Do not open ffplay (the `.ts` is still saved) |

---

## Logs and captures

Every run of `1_up_environment.sh` writes its logs to
`traffic_logs/run_<YYYYmmdd_HHMMSS>/`, so CAN and AVTP data of the same run
stay together:

| File | Written by | When |
|---|---|---|
| `can.log` | `candump` on `vcan0` | always |
| `avtp.pcap` | `tcpdump` on `br0` (switch namespace) | `--avtp` |
| `tcpdump.log` | `tcpdump` messages | `--avtp` |
| `avtp_stream.ts` | receiver in the vehicle controls module | `--avtp` |

The folder of the latest run is stored in `traffic_logs/.current_run` and is
printed by both `1_up_environment.sh` and `2_down_environment.sh`. Files
written by root processes (`avtp.pcap`, `avtp_stream.ts`) are owned by root but
readable by everyone.

Play back the received video:

```bash
ffplay traffic_logs/run_<timestamp>/avtp_stream.ts
```

---

## Running the receiver standalone

For debugging, the receiver can also run on its own while the environment is
up with `--avtp` (stop the one inside the vehicle controls module first, or use
another interface, as both would save to the same file):

```bash
sudo -E DISPLAY=$DISPLAY PYTHONPATH=. "$CONDA_PREFIX/bin/python" \
    avtp_network/receiver.py -i veth-r -o traffic_logs/run_<timestamp>
```

| Option | Default | Description |
|---|---|---|
| `--interface` / `-i` | `veth-r` | Network interface to listen on |
| `--output-dir` / `-o` | *(none)* | Save the stream as `<dir>/avtp_stream.ts` |
| `--timeout` / `-t` | *(none)* | Stop after N seconds without packets |
| `--no-video-window` | off | Do not open ffplay |

---

## Inspecting the traffic

Live view at the switch, in the terminal:

```bash
sudo ip netns exec switch tcpdump -i br0 -e ether proto 0x22F0
```

### Live in Wireshark

While the environment is up with `--avtp`, Wireshark can show the stream live.
Pick one of the following:

```bash
# 1. On a host interface: veth-r (receiver side) or veth-s (sender side)
wireshark -k -i veth-r -f "ether proto 0x22F0"

# 2. At the switch: br0 is inside the "switch" namespace, so pipe tcpdump in
sudo ip netns exec switch tcpdump -i br0 -U -w - ether proto 0x22F0 | wireshark -k -i -

# 3. Follow the capture file of the current run while it is being written
tail -c +1 -f traffic_logs/run_<timestamp>/avtp.pcap | wireshark -k -i -
```

Option 1 needs root, or your user in the `wireshark` group
(`sudo usermod -aG wireshark $USER`, then log in again). Without it, the
Wireshark GUI shows "You don't have permission to capture on local interfaces"
and hides `veth-r`/`veth-s` from the interface list. Once the permission is set,
you can also just pick `veth-r` or `veth-s` on the Wireshark welcome screen. Use the display filter
`ieee1722` to show only AVTP frames. The video stream produces a high
frame rate, so pause the capture to inspect individual packets.

### From the recorded capture

```bash
tshark -r traffic_logs/run_<timestamp>/avtp.pcap -c 5
wireshark traffic_logs/run_<timestamp>/avtp.pcap
```

Wireshark has a built-in IEEE 1722 dissector and decodes the AVTP header,
stream ID and sequence numbers directly from the capture.
