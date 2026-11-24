"""Tests for the AVTP receiver packet handling (no network, no ffplay)."""
from avtp_network.avtp import fragment_mpegts_stream
from avtp_network.receiver import ReceiverState

SRC_MAC = "02:00:00:00:00:01"
STREAM_ID = 0xAABBCCDDEEFF0001


def _ts_stream(n_blocks: int) -> bytes:
    """Build n 192-byte blocks: 4-byte SPH + 188-byte TS packet (sync 0x47, counter in payload)."""
    blocks = []
    for i in range(n_blocks):
        ts = bytes([0x47, 0x01, 0x00, 0x10]) + bytes([i & 0xFF]) * 184
        blocks.append(b"\x00\x00\x00\x00" + ts)
    return b"".join(blocks)


def _expected_ts(stream: bytes) -> bytes:
    """MPEG-TS bytes as the receiver should extract them (SPH headers stripped)."""
    return b"".join(stream[i + 4 : i + 192] for i in range(0, len(stream), 192))


def test_ts_payload_round_trips_and_reaches_callback(tmp_path):
    stream = _ts_stream(8)  # 4 packets of 2 blocks
    packets = fragment_mpegts_stream(stream, STREAM_ID, seq_counter=250, src_mac=SRC_MAC)
    assert len(packets) == 4

    received = []
    out = tmp_path / "avtp_stream.ts"
    state = ReceiverState(output_path=out, video_window=False, on_ts_data=received.append)
    for pkt in packets:
        state.handle_packet(pkt)
    state.close()

    assert b"".join(received) == _expected_ts(stream)
    assert out.read_bytes() == _expected_ts(stream)
    assert state.packets_received == 4
    assert state.packets_lost == 0  # sequence wraps 250..253 without loss


def test_sequence_gap_counts_lost_packets():
    packets = fragment_mpegts_stream(_ts_stream(8), STREAM_ID, seq_counter=0, src_mac=SRC_MAC)
    state = ReceiverState(video_window=False)
    state.handle_packet(packets[0])
    state.handle_packet(packets[3])  # skip seq 1 and 2
    assert state.packets_lost == 2
    assert state.packets_received == 2


def test_short_or_invalid_packets_are_ignored():
    state = ReceiverState(video_window=False)
    state.handle_packet(b"\x00" * 100)
    state.handle_packet(b"\x00" * 300)  # long enough but no 0x47 sync byte
    assert state.packets_received == 0
