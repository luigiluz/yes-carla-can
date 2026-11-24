#!/usr/bin/env python3
"""
receiver.py — AVTP MPEG-TS Receiver (Live FFplay Display)
=========================================================
Recebe pacotes AVTP MPEG-TS da rede e os envia em tempo real
para o 'ffplay' através de um sub-processo via PIPE (stdin).

Can be used in two ways:

* As a library: ``AvtpReceiver`` runs the receive loop in a background thread
  so it can live inside another module (e.g. the vehicle controls module).
  Each chunk of MPEG-TS data is also handed to an optional ``on_ts_data``
  callback (e.g. a decision engine).
* As a standalone script (``python avtp_network/receiver.py``).

Options
-------
    --interface         Network interface to listen on     (default: veth-r)
    --output-dir        Directory to save the stream as avtp_stream.ts (optional)
    --timeout           Stop after N seconds of silence    (default: off)
    --no-video-window   Do not open the live ffplay window
"""
from __future__ import annotations

import argparse
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from avtp_network.avtp import AVTP_ETHERTYPE, parse_mpegts_stream_packet

DEFAULT_INTERFACE = "veth-r"
STREAM_FILENAME = "avtp_stream.ts"


# ── Argument parsing ──────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="AVTP MPEG-TS Video Receiver with FFplay")
    parser.add_argument("-i", "--interface", default=DEFAULT_INTERFACE, help=f"Network interface to listen on (default: {DEFAULT_INTERFACE})")
    parser.add_argument("-o", "--output-dir", default=None, help=f"Directory to save the video stream to as {STREAM_FILENAME} (optional)")
    parser.add_argument("-t", "--timeout", type=float, default=None, help="Stop after this many seconds without packets (optional)")
    parser.add_argument("--no-video-window", action="store_true", help="Do not open the live ffplay window")
    return parser.parse_args()


# ── Receiver state ────────────────────────────────────────────────────────────

class ReceiverState:
    """
    Acumula os blocos MPEG-TS recebidos -> jitter buffer -> envia pro ffplay,
    pro disco (arquivo .ts) e pro callback ``on_ts_data``.
    """

    def __init__(
        self,
        output_path: Path | None = None,
        video_window: bool = True,
        on_ts_data: Optional[Callable[[bytes], None]] = None,
    ):
        self.packets_received = 0
        self.bytes_received = 0
        self.start_time = time.time()

        self.last_sequence_num = None
        self.packets_lost = 0

        self.on_ts_data = on_ts_data

        # IEC 61883-4 Annex A De-Jitter Buffer (3264 bytes) ---> reduzido para baixar a latencia na veth
        self.jitter_buffer = bytearray()
        self.is_buffered = False
        self.JITTER_BUFFER_SIZE = 3264

        self.out_file = None
        if output_path:
            self.out_file = open(output_path, "wb")
            print(f"  [i] Cópia em disco sendo salva em: {output_path.resolve()}")

        self.ffplay_proc = None
        if video_window:
            self._start_ffplay()

    def _start_ffplay(self):
        # Comando ffplay lendo diretamente da entrada padrão (pipe:0)
        ffplay_cmd = [
            "ffplay",
            "-window_title", "AVTP Live Stream (FFplay)",
            "-probesize", "150000",         # Aumentado para 150KB para ler SPS/PPS sem erro de rate
            "-analyzeduration", "500000",   # 0.5 segundo de análise para garantir sincronismo
            "-fflags", "nobuffer+fastseek", # Minimiza o atraso (buffering) do vídeo ao vivo
            "-flags", "low_delay",          # Força decodificação de baixa latência
            "-framedrop",                   # Descarta quadros atrasados para não travar a GUI
            "-f", "mpegts",                 # Força o demuxer MPEG-TS
            "-i", "pipe:0",                 # Lê do PIPE recebido do Python
            "-an",                          # Desativa áudio e elimina os avisos do PulseAudio
        ]

        try:
            self.ffplay_proc = subprocess.Popen(
                ffplay_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=None,
                bufsize=0,
            )
        except OSError as exc:
            print(f"\n  [!] ERRO ao iniciar o ffplay: {exc}")
            self.ffplay_proc = None
            return

        # Pequena pausa para verificar se o ffplay não morreu na largada
        time.sleep(0.2)
        if self.ffplay_proc.poll() is not None:
            print("\n  [!] ERRO: o ffplay encerrou logo após iniciar (veja a saída acima).")
            self.ffplay_proc = None

    def handle_packet(self, raw_pkt: bytes):
        # 1. Validação de tamanho mínimo L2 completo (Ethernet 14B + AVTP 24B + CIP 8B + SPH 4B + TS 188B = 238B)
        if len(raw_pkt) < 238:
            return

        # 2. Tenta extrair o payload MPEG-TS (50B de offset)
        ts_data = parse_mpegts_stream_packet(raw_pkt)
        if ts_data is None:
            return  # Descarta se não houver o byte de sincronismo 0x47 no offset correto

        # 3. Checagem de Perda de Pacotes (Apenas para pacotes com MPEG-TS válido)
        current_seq = raw_pkt[16]
        if self.last_sequence_num is not None:
            expected_seq = (self.last_sequence_num + 1) & 0xFF
            if current_seq != expected_seq:
                lost = (current_seq - expected_seq) & 0xFF
                self.packets_lost += lost
                print(
                    f"  [!] PERDA DETECTADA: Esperado {expected_seq:>3} "
                    f"| Recebido {current_seq:>3} | Perdidos neste salto: {lost}"
                )
        self.last_sequence_num = current_seq

        # 4. Atualização de estatísticas do receiver
        self.packets_received += 1
        self.bytes_received += len(ts_data)

        # Gravação em disco se a opção --output-dir for usada
        if self.out_file:
            self.out_file.write(ts_data)

        # Entrega os dados para quem consome o stream (ex.: decision engine)
        if self.on_ts_data is not None:
            try:
                self.on_ts_data(ts_data)
            except Exception as exc:
                print(f"  [!] Erro no callback on_ts_data: {exc}")

        # Envio para o ffplay via PIPE (stdin)
        if self.ffplay_proc and self.ffplay_proc.poll() is None:
            try:
                if not self.is_buffered:
                    self.jitter_buffer.extend(ts_data)
                    if len(self.jitter_buffer) >= self.JITTER_BUFFER_SIZE:
                        self.ffplay_proc.stdin.write(self.jitter_buffer)
                        self.ffplay_proc.stdin.flush()
                        self.is_buffered = True
                        self.jitter_buffer.clear()
                else:
                    self.ffplay_proc.stdin.write(ts_data)
                    self.ffplay_proc.stdin.flush()
            except (BrokenPipeError, OSError):
                pass

        # Log a cada 100 pacotes válidos recebidos
        if self.packets_received % 100 == 0:
            elapsed = time.time() - self.start_time
            rate_kbps = (self.bytes_received * 8 / 1000) / elapsed if elapsed > 0 else 0
            print(
                f"  [RX TS] Pacotes: {self.packets_received:>6}"
                f" | Total: {self.bytes_received / 1024:>7.1f} KB"
                f" | Taxa: {rate_kbps:>6.1f} kbps"
                f" | Perdas: {self.packets_lost:>4}"
            )

    def close(self):
        """Fecha o arquivo e o ffplay ao encerrar."""
        if self.out_file:
            self.out_file.close()
            self.out_file = None

        if self.ffplay_proc:
            try:
                if self.ffplay_proc.stdin:
                    self.ffplay_proc.stdin.close()
                self.ffplay_proc.terminate()
                self.ffplay_proc.wait(timeout=1)
            except Exception:
                pass
            self.ffplay_proc = None

    def print_summary(self):
        elapsed = time.time() - self.start_time
        avg_rate = (self.bytes_received * 8 / 1000) / elapsed if elapsed > 0 else 0

        print("\n")
        print("=" * 65)
        print("  Reception Summary")
        print("=" * 65)
        print(f"  Packets received : {self.packets_received}")
        print(f"  Packets lost     : {self.packets_lost}")
        print(f"  Bytes received   : {self.bytes_received:,} B")
        print(f"  Elapsed time     : {elapsed:.2f} s")
        print(f"  Average Rate     : {avg_rate:.1f} kbps")
        print("=" * 65)


# ── Receiver (background thread) ──────────────────────────────────────────────

class AvtpReceiver:
    """
    Receives the AVTP MPEG-TS stream on ``interface`` in a background thread.

        rx = AvtpReceiver("veth-r", output_dir=run_dir, on_ts_data=callback)
        rx.start()      # raises OSError if the raw socket cannot be opened
        ...
        rx.stop()       # closes socket, .ts file and ffplay; prints the summary
    """

    POLL_INTERVAL = 0.5  # seconds; how often the loop checks for stop()

    def __init__(
        self,
        interface: str = DEFAULT_INTERFACE,
        output_dir: str | Path | None = None,
        video_window: bool = True,
        on_ts_data: Optional[Callable[[bytes], None]] = None,
        timeout: float | None = None,
    ):
        self.interface = interface
        self.output_dir = Path(output_dir) if output_dir else None
        self.video_window = video_window
        self.on_ts_data = on_ts_data
        self.timeout = timeout

        self.state: ReceiverState | None = None
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    @property
    def stats(self) -> dict:
        st = self.state
        if st is None:
            return {"packets_received": 0, "packets_lost": 0, "bytes_received": 0}
        return {
            "packets_received": st.packets_received,
            "packets_lost": st.packets_lost,
            "bytes_received": st.bytes_received,
        }

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        # Criar Socket RAW nativo do Linux focado no EtherType AVTP (0x22F0)
        sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(AVTP_ETHERTYPE))
        try:
            sock.bind((self.interface, AVTP_ETHERTYPE))
            # Expande o buffer de recepção no kernel para 16MB para evitar perdas
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 16 * 1024 * 1024)
            sock.settimeout(self.POLL_INTERVAL)
        except Exception:
            sock.close()
            raise
        self._sock = sock

        output_path = None
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            output_path = self.output_dir / STREAM_FILENAME

        self.state = ReceiverState(
            output_path=output_path,
            video_window=self.video_window,
            on_ts_data=self.on_ts_data,
        )

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="avtp-receiver", daemon=True)
        self._thread.start()
        print(f"  [i] Listening for AVTP MPEG-TS stream on '{self.interface}'...")

    def _loop(self):
        last_packet = time.time()
        while not self._stop_event.is_set():
            try:
                raw_pkt, _ = self._sock.recvfrom(2048)
            except socket.timeout:
                if self.timeout and time.time() - last_packet >= self.timeout:
                    print("\n  [i] Timeout atingido sem pacotes. Encerrando recepção.")
                    break
                continue
            except OSError:
                break  # socket closed
            last_packet = time.time()
            self.state.handle_packet(raw_pkt)

    def wait(self):
        """Block until the receive loop ends (timeout) or Ctrl-C."""
        while self.is_running():
            self._thread.join(timeout=0.5)

    def stop(self):
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=2)
        self._thread = None
        if self._sock:
            self._sock.close()
            self._sock = None
        if self.state:
            self.state.close()
            self.state.print_summary()


# ── Main ──────────────────────────────────────────────────────────────────────

def run(args):
    print("=" * 65)
    print("  AVTP Video Receiver (MPEG-TS Stream)")
    print("=" * 65)
    print(f"  Interface : {args.interface}")
    print(f"  Output dir: {args.output_dir or '(none)'}")
    print(f"  Timeout   : {args.timeout or 'none'}")
    print(f"  Video     : {'off' if args.no_video_window else 'ffplay'}")
    print("=" * 65)
    print()

    receiver = AvtpReceiver(
        interface=args.interface,
        output_dir=args.output_dir,
        video_window=not args.no_video_window,
        timeout=args.timeout,
    )
    try:
        receiver.start()
    except OSError as e:
        print(f"  [!] Erro ao abrir socket RAW na interface '{args.interface}': {e}")
        sys.exit(1)

    # SIGTERM (e.g. from 2_down_environment.sh) also shuts down cleanly
    def _on_sigterm(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, _on_sigterm)

    print("  (Ctrl-C to quit)\n")
    try:
        receiver.wait()
    except KeyboardInterrupt:
        pass
    finally:
        receiver.stop()


if __name__ == "__main__":
    run(parse_args())

## rcvbuf
# Atua no nível da placa de rede / sistema operacional. Ele evita que o Kernel do Linux descarte pacotes chegados na interface caso a aplicação Python demore alguns milissegundos para processar o loop.

## Jitter Buffer de 3264B
# Atua na lógica do código antes de entregar a mídia ao ffplay. Ele garante que o decodificador de vídeo não sofra com underrun.
