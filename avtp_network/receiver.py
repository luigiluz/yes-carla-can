#!/usr/bin/env python3
"""
receiver.py — AVTP MPEG-TS Receiver (Live FFplay Display)
=========================================================
Recebe pacotes AVTP MPEG-TS da rede e os envia em tempo real
para o 'ffplay' através de um sub-processo via PIPE (stdin).

Options
-------
    --interface     Network interface to listen on     (default: veth-r)
    --output-dir    Directory to save received frames  (optional)
    --timeout       Stop after N seconds of silence    (default: off)
"""
from __future__ import annotations

import argparse
import signal
import time
import subprocess  
from pathlib import Path
import socket
import sys
from datetime import datetime

from avtp_network.avtp import parse_mpegts_stream_packet


# ── Argument parsing ──────────────────────────────────────────────────────────
AVTP_ETHERTYPE = 0x22F0  # EtherType do IEEE 1722 / AVTP

def parse_args():
    parser = argparse.ArgumentParser(description="AVTP MPEG-TS Video Receiver with FFplay")
    parser.add_argument("-i", "--interface", default="veth-r", help="Network interface to listen on (default: veth-r)")
    parser.add_argument("-o", "--output-dir", default=None, help="Directory to save video stream to disk (optional)")
    parser.add_argument("-t", "--timeout", type=float, default=None, help="Stop sniffing after this many seconds of inactivity (optional)")
    return parser.parse_args()



# ── Receiver state ────────────────────────────────────────────────────────────

class ReceiverState:
    """
    Acumula os blocos MPEG-TS recebidos -> jitter buffer-> envia pro ffplay e pro discom arquivo de vídeo (.ts).
    """

    def __init__(self, output_dir: Path | None = None, output_filename: str = "output_stream.ts"):
        self.packets_received = 0
        self.bytes_received = 0
        self.start_time = time.time()

        self.last_sequence_num = None
        self.packets_lost = 0

        #IEC 61883-4 Annex A De-Jitter Buffer (3264 bytes)---> reduzido para baixar a latencia na veth
        self.jitter_buffer = bytearray()
        self.is_buffered = False
        self.JITTER_BUFFER_SIZE = 3264 
        
        self.out_file = None
        if output_dir:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
            
            output_path = output_dir / f"output_stream_{timestamp}.ts"
            self.out_file = open(output_path, "wb")
            print(f"  [i] Cópia em disco sendo salva em: {output_path.resolve()}")
        
        
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
            "-i", "pipe:0",                  # Lê do PIPE recebido do Python
            "-an",                          # Desativa áudio e elimina os avisos do PulseAudio
        ]

        # Abre o processo FFplay
        self.ffplay_proc = subprocess.Popen(
            ffplay_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=None,
            bufsize=0
        )

        # Pequena pausa para verificar se o ffplay não morreu na largada
        time.sleep(0.2)
        if self.ffplay_proc.poll() is not None:
            _, err = self.ffplay_proc.communicate()
            print("\n  [!] ERRO ao iniciar o ffplay:")
            print(err.decode("utf-8", errors="replace"))


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
        """Fecha o arquivo ao encerrar o script."""
        if self.out_file:
            self.out_file.close()

        if hasattr(self, "ffplay_proc") and self.ffplay_proc:
            try:
                if self.ffplay_proc.stdin:
                    self.ffplay_proc.stdin.close()
                self.ffplay_proc.terminate()
                self.ffplay_proc.wait(timeout=1)
            except Exception:
                pass


# ── Main ──────────────────────────────────────────────────────────────────────

def run(args):
    
    output_dir = None
    if args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    state = ReceiverState(output_dir=output_dir)

    print("=" * 65)
    print("  AVTP Video Receiver (MPEG-TS Stream)")
    print("=" * 65)
    print(f"  Interface : {args.interface}")
    print(f"  Output dir: {args.output_dir or '(diretório atual)'}")
    print(f"  Timeout   : {args.timeout or 'none'}")
    print("=" * 65)
    print()


   # Criar Socket RAW nativo do Linux focado no EtherType AVTP (0x22F0)
    try:
        sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(AVTP_ETHERTYPE))
        sock.bind((args.interface, AVTP_ETHERTYPE))
        # Expande o buffer de recepção no kernel para 16MB para evitar perdas
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 16 * 1024 * 1024)
    except Exception as e:
        print(f"  [!] Erro ao abrir socket RAW na interface '{args.interface}': {e}")
        sys.exit(1)

    if args.timeout:
        sock.settimeout(args.timeout)

    stop_requested = False



    def _sigint_handler(sig, frame):
        nonlocal stop_requested
        stop_requested = True


    signal.signal(signal.SIGINT, _sigint_handler)

    print("  Listening for AVTP MPEG-TS stream... (Ctrl-C to quit)\n")

    try:
        while not stop_requested:
            try:
                raw_pkt, _ = sock.recvfrom(2048)
                state.handle_packet(raw_pkt)
            except socket.timeout:
                print("\n  [i] Timeout atingido sem pacotes. Encerrando recepção.")
                break
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
        state.close()


    elapsed = time.time() - state.start_time
    avg_rate = (state.bytes_received * 8 / 1000) / elapsed if elapsed > 0 else 0

    print("\n")
    print("=" * 65)
    print("  Reception Summary")
    print("=" * 65)
    print(f"  Packets received : {state.packets_received}")
    print(f"  Bytes received   : {state.bytes_received:,} B")
    print(f"  Elapsed time     : {elapsed:.2f} s")
    print(f"  Average Rate     : {avg_rate:.1f} kbps")
    print("=" * 65)

  
if __name__ == "__main__":
    args = parse_args()
    run(args)

##rcvbuf 
# Atua no nível da placa de rede / sistema operacional. Ele evita que o Kernel do Linux descarte pacotes chegados na interface caso a aplicação Python demore alguns milissegundos para processar o loop da função sniff().



##Jitter Buffer de 3264B
#Atua na lógica do seu código antes de entregar a mídia ao ffplay. Ele garante que o decodificador de vídeo não sofra com underrun
