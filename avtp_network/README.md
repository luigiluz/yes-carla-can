# virtual-avtp-network

A self-contained demonstration of **video transmission over the AVTP protocol
(IEEE 1722)** using Linux network namespaces and the
[Scapy](https://scapy.net/) packet-crafting library.

The goal is to be didactic: every layer of the stack — from the virtual
Ethernet wires up to the AVTP CVF header and image fragmentation — is
implemented explicitly so that each step can be inspected, captured, and
understood.

---

## Table of Contents

1. [Architecture](#architecture)
2. [How It Works](#how-it-works)
3. [Project Structure](#project-structure)
4. [Prerequisites](#prerequisites)
5. [Quick Start](#quick-start)
6. [Usage Reference](#usage-reference)
7. [Inspecting the Traffic](#inspecting-the-traffic)

---

## Architecture

```
 ┌─────────────────────┐        ┌──────────────────────────────┐        ┌─────────────────────┐
 │    sender  (ns)      │        │         switch  (ns)         │        │   receiver  (ns)     │
 │                      │        │                              │        │                      │
 │  sender.py           │        │  Linux bridge  br0           │        │  receiver.py         │
 │  (reads PNG frames,  │        │  (forwards L2 frames,        │        │  (reassembles AVTP   │
 │   builds AVTP pkts,  │        │   no IP, no STP)             │        │   fragments, renders │
 │   sends via Scapy)   │        │                              │        │   frames in OpenCV)  │
 │                      │        │  ┌──────────┐                │        │                      │
 │        veth-s ───────┼────────┼─►│veth-s-sw │                │        │                      │
 │                      │        │  └────┬─────┘                │        │                      │
 │                      │        │       │  br0                 │        │                      │
 │                      │        │  ┌────┴─────┐                │        │                      │
 │                      │        │  │veth-r-sw │────────────────┼────────┼─── veth-r            │
 │                      │        │  └──────────┘                │        │                      │
 └─────────────────────┘        └──────────────────────────────┘        └─────────────────────┘

 EtherType: 0x22F0 (AVTP)   ·   Pure Layer 2   ·   No IP addresses
```

Three Linux **network namespaces** act as isolated network stacks:

| Namespace | Role | Interface |
|---|---|---|
| `sender` | Reads images and transmits AVTP packets | `veth-s` |
| `switch` | Bridges traffic between sender and receiver | `veth-s-sw`, `veth-r-sw`, `br0` |
| `receiver` | Receives, reassembles, and displays frames | `veth-r` |

The namespaces are connected by two **veth (virtual Ethernet) pairs** — a
Linux primitive that works like a patch cable: anything written into one end
comes out the other. The switch namespace hosts a software **bridge** (`br0`)
that forwards Ethernet frames between the two veth pairs, just as a real
Ethernet switch would.

No IP addresses are assigned anywhere. AVTP is a **Layer-2 protocol**
(EtherType `0x22F0`) and travels directly inside Ethernet frames.

---

## How It Works

### 1. AVTP CVF — the protocol layer (`avtp.py`)

AVTP (**Audio Video Transport Protocol**, IEEE 1722) is designed to carry
time-sensitive multimedia streams over Ethernet. This demo uses the
**CVF (Compressed Video Format)** subtype (`0x02`), which is meant for
carrying compressed video payloads such as MJPEG or H.264.

A custom Scapy `AVTP` packet class is defined with the full CVF header
(24 bytes):

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|    subtype    |sv| ver |mr|r|tv|tu| sequence_num |   reserved  |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                          stream_id (64 bits)                   |
|                                                                |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       avtp_timestamp                           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|    format     | format_subtype|           reserved             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|        stream_data_length     |M|   evt   |     reserved       |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

Key fields:
- **`subtype`** `0x02` — identifies this as a CVF stream
- **`sv`** — stream ID is valid
- **`tv`** — the `avtp_timestamp` field is valid
- **`sequence_num`** — per-stream packet counter (wraps at 255); the receiver
  can use this to detect dropped packets
- **`stream_id`** — 64-bit identifier for the AVTP stream
- **`avtp_timestamp`** — presentation timestamp (low 32 bits of nanoseconds)
- **`marker_bit` (M)** — set to `1` on the **last fragment** of each image
  frame, signalling the receiver to begin reassembly

### 2. Fragmentation

PNG images from the input dataset are typically hundreds of kilobytes — far
larger than a single Ethernet frame (MTU 1500 bytes). Each image is therefore
split into chunks before transmission.

Every AVTP packet payload carries a **10-byte fragment sub-header** followed
by a raw chunk of the image:

```
[ frame_num (2B) | fragment_offset (4B) | total_size (4B) ][ image chunk ]
```

- **`frame_num`** — which image frame this fragment belongs to (wraps at 65535)
- **`fragment_offset`** — byte position of this chunk within the full image
- **`total_size`** — total byte length of the full image

The receiver buffers incoming fragments indexed by `frame_num`. When a packet
arrives with `marker_bit = 1`, reassembly is triggered: the chunks are placed
at their correct offsets into a byte buffer, which is then decoded as a PNG.

### 3. Sender (`sender.py`)

```
PNG files on disk
      │
      ▼
 read_bytes()
      │
      ▼
 fragment_image()  ──►  list of Ether / AVTP packets
                              │
                              ▼
                         sendp()  ──►  veth-s  ──►  br0  ──►  veth-r
```

The sender reads frames at a configurable rate (`--fps`), fragments each one,
and transmits the packet list in a single `sendp()` call. A frame-period sleep
maintains the target frame rate.

### 4. Receiver (`receiver.py`)

```
veth-r
  │
  ▼
sniff(filter="ether proto 0x22F0")
  │
  ▼
parse_avtp_fragment()  ──►  buffer[frame_num].append(fragment)
                                      │  (on marker_bit = 1)
                                      ▼
                           reassemble_fragments()
                                      │
                                      ▼
                           cv2.imdecode()  ──►  cv2.imshow()
```

Scapy's `sniff()` runs with a BPF filter that passes only AVTP EtherType
frames, keeping the callback lean. Each completed frame is decoded from PNG
bytes with OpenCV and displayed in a live window with an on-screen HUD showing
frame number, fragment count, and running FPS.

---

## Project Structure

```
virtual-avtp-network/
├── setup.sh          # Network namespace + bridge setup / teardown
├── avtp.py           # AVTP CVF Scapy layer + fragmentation helpers
├── sender.py         # AVTP video sender
├── receiver.py       # AVTP video receiver with OpenCV display
├── requirements.txt  # Python dependencies
└── _out/
    └── camera/       # Input PNG frames (1,645 files)
```

---

## Prerequisites

- Linux (namespaces and veth require the Linux kernel)
- `iproute2` (`ip` command) — standard on most distros
- `tcpdump` — for the optional packet capture
- Python 3.11+
- `sudo` / root access — raw socket operations require elevated privileges

---

## Quick Start

**1. Clone and set up the Python environment**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**2. Create the virtual network**

```bash
sudo bash setup.sh
```

**3. Start the receiver** *(in one terminal)*

```bash
sudo ip netns exec receiver .venv/bin/python3 receiver.py
```

An OpenCV window will open and wait for incoming frames.

**4. Start the sender** *(in a second terminal)*

```bash
sudo ip netns exec sender .venv/bin/python3 sender.py
```

Frames will start appearing in the receiver window immediately.

**5. Tear down**

```bash
sudo bash setup.sh --teardown
```

---

## Usage Reference

### `setup.sh`

```
sudo bash setup.sh [--capture] [--teardown]
```

| Flag | Description |
|---|---|
| *(none)* | Create namespaces, veth pairs, and bridge |
| `--capture` | Also start `tcpdump` on `br0`; write AVTP frames to a timestamped `.pcap` file |
| `--teardown` | Delete all namespaces and stop any running capture |



### `receiver.py`

```
sudo ip netns exec receiver .venv/bin/python3 receiver.py [options]

```

| Option | Default | Description |
|---|---|---|
| `--interface` / `-i` | `veth-r` | Network interface to listen on |
| `--output-dir` / `-o` | *(none)* | Save each received frame as a `.png` file |
| `--timeout` / `-t` | *(none)* | Stop after N seconds of no traffic |


### `sender.py`

```
sudo ip netns exec sender .venv/bin/python3 sender.py [options]
```

| Option | Default | Description |
|---|---|---|
| `--interface` / `-i` | `veth-s` | Network interface to send on |
| `--fps` / `-f` | `30` | Target transmission frame rate |
| `--images-dir` / `-d` | `_out/camera` | Directory containing `.png` frames |
| `--stream-id` / `-s` | `0xAABBCCDDEEFF0001` | 64-bit AVTP stream identifier (hex) |
| `--loop` / `-l` | off | Loop through all frames indefinitely |

---

## Inspecting the Traffic

### Live terminal view

```bash
sudo ip netns exec switch tcpdump -i br0 -e ether proto 0x22F0
```

### Record to PCAP (automatic)

```bash
sudo bash setup.sh --capture
# ... run sender and receiver ...
sudo bash setup.sh --teardown
# output: avtp_capture_<timestamp>.pcap
```

### Open in Wireshark

```bash
wireshark avtp_capture_<timestamp>.pcap
```

Wireshark has a built-in AVTP dissector (available from version 3.x). It will
decode the CVF subtype, stream ID, sequence numbers, and timestamps directly
from the capture file.
