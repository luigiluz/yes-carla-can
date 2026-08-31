import os
import sys
import time
import weakref
import socket
import struct

import numpy as np
import pygame
import carla


PATH_AVTP = "/home/ju/virtual-avtp-network"  # Coloque o caminho absoluto da sua pasta do AVTP aqui
if PATH_AVTP not in sys.path:
    sys.path.append(PATH_AVTP)


import cv2
import avtp as avtp_lib
from scapy.all import sendp, get_if_hwaddr

class MPEGTSStreamEncoder:
    """
    Encoder simplificado e ultra-rápido de MPEG-TS (ISO/IEC 13818-1) para AVTP.
    Empacota imagens em blocos de 192 bytes:
      - 4 bytes: Source Packet Header (SPH Timestamp)
      - 188 bytes: MPEG-TS Packet (Sync byte 0x47 + Header + Payload)
    """
    def __init__(self, pid=0x18):
        self.pid = pid
        self.continuity_counter = 0

    def encode_frame_to_ts_blocks(self, bgra_array, quality=50):
        # 1. Comprime o frame para reduzir tamanho
        success, encoded_img = cv2.imencode(".jpg", bgra_array, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not success:
            return b""
        
        payload_data = encoded_img.tobytes()
        
        # 2. Divide em blocos de payload MPEG-TS (184 bytes de dados por pacote TS)
        ts_blocks = []
        sph_timestamp = int((time.time() * 1000000)) & 0xFFFFFFFF  # Timestamp em microsegundos
        
        chunk_size = 184
        for i in range(0, len(payload_data), chunk_size):
            chunk = payload_data[i:i + chunk_size]
            if len(chunk) < chunk_size:
                chunk = chunk.ljust(chunk_size, b"\x00")  # Padding com zeros até 184B
            
            # Cabeçalho MPEG-TS (4 Bytes):
            # Byte 0: 0x47 (Sync Byte obrigatório ISO 13818-1)
            # Bytes 1-2: Flags + PID (0x18)
            # Byte 3: 0x10 (Payload only) | Continuity Counter (0..15)
            # 0x00 representa as flags (ou 0x40 se for o início de uma unidade PES)
            pusi_flag = 0x40 if i == 0 else 0x00
            byte1 = pusi_flag | ((self.pid >> 8) & 0x1F)

            ts_header = struct.pack(
                "!BBBB",
                0x47,
                byte1,
                self.pid & 0xFF,
                0x10 | (self.continuity_counter & 0x0F),
            )

            self.continuity_counter = (self.continuity_counter + 1) & 0x0F
            
            ts_packet_188 = ts_header + chunk  # 188 Bytes
            
            # Cabeçalho SPH Timestamp de 4 Bytes do IEC 61883-4
            sph_header = struct.pack("!I", sph_timestamp)
            
            # Bloco final da IEC 61883-4 = 192 Bytes
            ts_blocks.append(sph_header + ts_packet_188)
            
        return b"".join(ts_blocks)


class RGBCameraSensor(object):
    """
    Dedicated front-facing RGB camera sensor.

    Stores the latest frame both as a pygame Surface (for on-screen display)
    and as a raw numpy array (for data export / ML pipelines).

    ── How to access the camera data ──────────────────────────────────────────

    From anywhere that holds a reference to this sensor object:

        # Latest frame as a numpy uint8 array shaped (H, W, 3) in RGB order
        frame_rgb = world.rgb_camera_sensor.array

        # Save the current frame to a PNG file (requires Pillow):
        from PIL import Image
        img = Image.fromarray(frame_rgb)
        img.save("frame.png")

        # Or use OpenCV:
        import cv2
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        cv2.imwrite("frame.png", frame_bgr)

    To export every frame automatically, set ``recording = True`` on the
    sensor instance.  Frames will be saved under the ``_out/camera/``
    directory as ``<frame_number>.png`` via CARLA's built-in save helper:

        world.rgb_camera_sensor.recording = True   # start
        world.rgb_camera_sensor.recording = False  # stop

    ───────────────────────────────────────────────────────────────────────────
    """

    # Resolution of the camera (pixels).  Must match or be smaller than the
    # pygame display so the PiP overlay fits on screen.
    IMAGE_WIDTH = 640
    IMAGE_HEIGHT = 360

    def __init__(self, parent_actor, gamma_correction=2.2, stream_id="0xAABBCCDDEEFF0001", interface="veth-s"):
        self.sensor = None
        self.surface = None          # pygame.Surface, updated each frame
        self.array = None            # numpy (H, W, 3) uint8 RGB, updated each frame
        self.recording = False       # set True to auto-save every frame to disk

        self.enabled = True  # Flag de controle


        # ── Configurações de Rede AVTP ───────────────────────────────────────
        self.interface = interface
        self.stream_id = int(stream_id, 16)
        self.ts_encoder = MPEGTSStreamEncoder(pid=0x18)  # 24 muah

        try:
            self.src_mac = get_if_hwaddr(self.interface)
        except Exception as exc:
            print(f"[!] Erro ao ler MAC da interface '{self.interface}': {exc}")
            sys.exit(1)

        try:
            self.sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)
            self.sock.bind((self.interface, 0))
        except Exception as e:
            print(f"[!] Erro ao abrir RAW Socket na interface '{self.interface}': {e}")
            self.sock = None

        
        # Contadores do AVTP
        self.seq_counter = 0     # AVTP sequence_num (wraps at 255)
        self.frames_sent = 0
        self.pkts_sent = 0
        self.bytes_sent = 0
        self.start_time = time.time()
        # ─────────────────────────────────────────────────────────────────────



        self._parent = parent_actor

        bound_x = 0.5 + self._parent.bounding_box.extent.x
        bound_z = 0.5 + self._parent.bounding_box.extent.z

        world = self._parent.get_world()
        bp = world.get_blueprint_library().find('sensor.camera.rgb')
        bp.set_attribute('image_size_x', str(self.IMAGE_WIDTH))
        bp.set_attribute('image_size_y', str(self.IMAGE_HEIGHT))
        bp.set_attribute('fov', '90')
        if bp.has_attribute('gamma'):
            bp.set_attribute('gamma', str(gamma_correction))

        # Mount on the front hood of the vehicle, slightly elevated.
        spawn_transform = carla.Transform(
            carla.Location(x=bound_x + 0.3, z=bound_z + 0.1),
            carla.Rotation(pitch=0.0),
        )

        self.sensor = world.spawn_actor(
            bp,
            spawn_transform,
            attach_to=self._parent,
            attachment_type=carla.AttachmentType.Rigid,
        )

        weak_self = weakref.ref(self)
        self.sensor.listen(
            lambda image: RGBCameraSensor._on_image(weak_self, image)
        )



    def destroy(self):
        """Desliga o sensor da câmera, para o streaming AVTP e destrói o ator no CARLA."""
        # 1. Parar de escutar os dados da câmera no CARLA
        if self.sensor is not None:
            try:
                self.sensor.stop()
                self.sensor.destroy()
            except Exception as e:
                print(f"[!] Erro ao destruir o sensor da câmera: {e}")
            finally:
                self.sensor = None

        # 2. Fechar o socket de rede RAW
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
            finally:
                self.sock = None

        # 3. Limpar ponteiros de memória do PyGame e numpy
        self.surface = None
        self.array = None
        print("[+] Câmera RGB desativada e socket AVTP fechado com sucesso.")

    def toggle_camera(self):
        """Alterna o envio de imagens via AVTP e o processamento entre ligado/desligado."""
        self.enabled = not self.enabled
        status = "LIGADA (Transmitindo AVTP)" if self.enabled else "DESLIGADA (Pausada)"
        print(f"[*] Câmera RGB: {status}")
        


    def render(self, display, pos=(0, 0)):
        """Exibe a imagem na tela do Pygame."""
        if self.surface is not None:
            display.blit(self.surface, pos)


    @staticmethod
    def _on_image(weak_self, image):
        self = weak_self()
        if not self or not getattr(self, 'enabled', True):
            return

        # raw_data is a flat BGRA byte buffer; reshape to (H, W, 4).
        array = np.frombuffer(image.raw_data, dtype=np.uint8)
        array = np.reshape(array, (image.height, image.width, 4))


        # Mantém o BGRA apenas para o OpenCV codificar para JPEG
        bgra_array = array

       # Prepara a exibição no PyGame (Converte BGR -> RGB)
        if array is not None and len(array.shape) == 3 and array.shape[2] >= 3:
            # Pega os 3 canais e inverte BGR para RGB (::-1)
            rgb_array = array[:, :, :3][:, :, ::-1]
            self.array = rgb_array
            try:
                # Transpõe para o formato que a superfície do Pygame espera (Largura, Altura, 3)
                self.surface = pygame.surfarray.make_surface(rgb_array.swapaxes(0, 1))
            except Exception:
                pass


        # Codifica para o Padrão MPEG-TS ISO/IEC 13818-1 (Blocos de 192 Bytes)
        ts_stream_bytes = self.ts_encoder.encode_frame_to_ts_blocks(bgra_array, quality=50)
        if not ts_stream_bytes:
            return

        #Fragmenta o Stream MPEG-TS em Pacotes AVTP
        # Cada pacote AVTP vai conter 2 blocos de 192 bytes = 384 bytes de payload
        frame_num = self.frames_sent & 0xFFFF



        # Fragmenta o Stream MPEG-TS em Pacotes AVTP
        try:
            packets = avtp_lib.fragment_mpegts_stream(
                ts_bytes=ts_stream_bytes,
                stream_id=self.stream_id,
                seq_counter=self.seq_counter,
                src_mac=self.src_mac,
                blocks_per_pkt=2
            )
        except Exception as err:
            print(f"[!] Erro ao fragmentar MPEG-TS no avtp_lib: {err}")
            return

        if not packets:
            print("[!] AVISO: 'packets' retornou VAZIO do fragment_mpegts_stream!")
            return

        # Envia os fragmentos
        sent_count = 0
        try:
            if self.sock:
                for pkt in packets:
                    # Converte para bytes se for pacote Scapy, ou usa diretamente se já for bytes
                    pkt_bytes = bytes(pkt) if not isinstance(pkt, bytes) else pkt
                    self.sock.send(pkt_bytes)
                    sent_count += 1
            else:
                sendp(packets, iface=self.interface, verbose=0)
                sent_count = len(packets)
        except Exception as err:
            print(f"[!] Erro no socket.send: {err}")
            return

            

        # Atualiza os contadores internos
        self.seq_counter = (self.seq_counter + len(packets)) & 0xFF
        self.frames_sent += 1
        self.bytes_sent += len(ts_stream_bytes)
        self.pkts_sent += len(packets)

        elapsed = time.time() - self.start_time
        print(
            f"  [TX MPEG-TS] Frame {self.frames_sent:>5}"
            f"  {len(ts_stream_bytes):>7} B"
            f"  {len(packets):>3} pkts"
            f"  seq {frame_num:>5}"
            f"  elapsed {elapsed:>7.1f}s"
        )