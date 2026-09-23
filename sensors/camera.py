import os
import sys
import time
import weakref
import socket
import struct
import io


import numpy as np
import pygame
import carla
import av


from avtp_network import avtp as avtp_lib
from scapy.all import get_if_hwaddr
from fractions import Fraction

class MPEGTSStreamEncoder:
    """
    Encoder MPEG-TS profissional baseado no FFmpeg (PyAV) para AVTP IEC 61883-4.
    Converte frames de imagens em um fluxo de vídeo H.264 empacotado em 
    blocos MPEG-TS de 192 bytes (4B SPH Timestamp + 188B TS Packet) configurado com injeção contínua de SPS/PPS.
    """
    def __init__(self, width=470, height=200, fps=30, pid=0x18):
        self.width = width
        self.height = height
        self.fps = fps
        self.pid = pid

        self.pts_counter = 0

        # 1. Buffer em memória onde o PyAV/FFmpeg irá escrever os blocos MPEG-TS
        self.output_buffer = io.BytesIO()

        # 2. Instancia o container MPEG-TS uma única vez
        self.container = av.open(
            self.output_buffer,
            mode="w",
            format="mpegts",
            options={"mpegts_flags": "resend_headers"}
        )


        # 4. Configurações de ultra-baixa latência
        codec_options = {
            "tune": "zerolatency",
            "preset": "ultrafast",
            "g": "5",                                           # Keyframe (I-frame) a cada 5 frames para recuperação rápida
            "keyint_min": "5",                                  # Intervalo MÍNIMO de 5 frames
            "sc_threshold": "0",                                # Desativa detecção de cena para manter Keyframes fixos
            "x264-params": "repeat-headers=1:aud=1:force-cfr=1" # Força injeção de SPS/PPS + Annex B
        }

        # 3. Cria a stream H.264 uma única vez
        self.stream = self.container.add_stream("h264", rate=self.fps, options=codec_options)
        self.stream.width = self.width
        self.stream.height = self.height
        self.stream.pix_fmt = "yuv420p"

    def encode_frame_to_ts_blocks(self, bgra_array):
        """
        Recebe a matriz BGRA (H, W, 4) do CARLA, codifica via FFmpeg e 
        retorna os blocos de 192 bytes prontos para o AVTP.
        
        """
        # Limpa o buffer de saída mantendo a mesma instância em memória
        self.output_buffer.seek(0)
        self.output_buffer.truncate(0)


        # 1. Converte a matriz BGRA para RGB (elimina o canal Alpha)
        rgb_array = bgra_array[:, :, :3][:, :, ::-1]

        # 2. Cria o Frame do PyAV
        frame = av.VideoFrame.from_ndarray(rgb_array, format="rgb24")
        frame.pts = self.pts_counter
        self.pts_counter += 1


        # 3. Codifica o frame com o FFmpeg e envia pra o container mpeg-ts 
        for packet in self.stream.encode(frame):
            self.container.mux(packet)

     
        raw_ts_bytes = self.output_buffer.getvalue()
        if not raw_ts_bytes:
            return b""

        # 4. Fatiamento em blocos IEC 61883-4 (192 Bytes = 4B SPH + 188B TS Packet)
        ts_blocks = []
        sph_timestamp = int(time.time() * 1000000) & 0xFFFFFFFF  # Microsegundos

        # Garante que os pacotes TS de 188 bytes recebam o SPH Header de 4 bytes
        for i in range(0, len(raw_ts_bytes), 188):
            ts_pkt_188 = raw_ts_bytes[i:i + 188]
            if len(ts_pkt_188) == 188:
                sph_header = struct.pack("!I", sph_timestamp)
                ts_blocks.append(sph_header + ts_pkt_188)

        return b"".join(ts_blocks)
    
    def close(self):
        """Fecha o container FFmpeg ao encerrar a execução."""
        if hasattr(self, 'container') and self.container:
            try:
                # Efetua o flush dos pacotes pendentes
                for packet in self.stream.encode():
                    self.container.mux(packet)
                self.container.close()
            except Exception as e:
                print(f"[!] Erro ao fechar o encoder PyAV: {e}")



class RGBCameraSensor(object):
    """
    Dedicated front-facing RGB camera sensor.


    To export every frame automatically, set ``recording = True`` on the
    sensor instance.  Frames will be saved under the ``_out/camera/``
    directory as ``<frame_number>.png`` via CARLA's built-in save helper:

        world.rgb_camera_sensor.recording = True   # start
        world.rgb_camera_sensor.recording = False  # stop

    ───────────────────────────────────────────────────────────────────────────
    """

    # Resolução REAL da imagem (para o Streaming H.264/AVTP ter alta qualidade)
    IMAGE_WIDTH = 960
    IMAGE_HEIGHT = 400

    # Resolução de EXIBIÇÃO no Pygame (pequena para não ocupar espaço na tela)
    DISPLAY_WIDTH = 470
    DISPLAY_HEIGHT = 200


    def __init__(self, parent_actor, gamma_correction=2.2, stream_id="0xAABBCCDDEEFF0001", interface="veth-s"):
        self.sensor = None
        self.surface = None          # pygame.Surface, updated each frame
        self.array = None            # numpy (H, W, 3) uint8 RGB, updated each frame
        self.recording = False       # set True to auto-save every frame to disk

        self.enabled = True  # Flag de controle


        # ── Configurações de Rede AVTP ───────────────────────────────────────
        self.interface = interface
        self.stream_id = int(stream_id, 16)
        self.ts_encoder = MPEGTSStreamEncoder(width=self.IMAGE_WIDTH,height=self.IMAGE_HEIGHT,fps=30,pid=0x18) # 24 muah

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
        bp.set_attribute('sensor_tick', '0.033333')

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

        # 2. Fechar o encoder MPEG-TS/PyAV
        if hasattr(self, 'ts_encoder') and self.ts_encoder:
            self.ts_encoder.close()

        # 3. Fechar o socket de rede RAW
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
            finally:
                self.sock = None

        # 4. Limpar ponteiros de memória do PyGame e numpy
        self.surface = None
        self.array = None
        print("[+] Câmera RGB desativada e socket AVTP fechado com sucesso.")

    def toggle_camera(self):
        """Alterna o envio de imagens via AVTP e o processamento entre ligado/desligado."""
        self.enabled = not self.enabled
        status = "LIGADA (Transmitindo AVTP)" if self.enabled else "DESLIGADA (Pausada)"
        print(f"[*] Câmera RGB: {status}")
        


    def render(self, display, pos=None):
        """Exibe a imagem na tela do Pygame."""
        if self.surface is not None:
            if pos is None:
                display_width = display.get_width()
                display_height = display.get_height()

                # Canto inferior direito
                pos = (display_width - self.DISPLAY_WIDTH, display_height - self.DISPLAY_HEIGHT)
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
                # 1. Cria a superfície no tamanho original (960x400)
                full_surface = pygame.surfarray.make_surface(rgb_array.swapaxes(0, 1))
                
                # 2. Redimensiona apenas para a tela do Pygame (470x200)
                self.surface = pygame.transform.scale(
                    full_surface, 
                    (self.DISPLAY_WIDTH, self.DISPLAY_HEIGHT)
                )
            except Exception:
                pass


        # Codifica para o Padrão MPEG-TS ISO/IEC 13818-1 (Blocos de 192 Bytes)
        ts_stream_bytes = self.ts_encoder.encode_frame_to_ts_blocks(bgra_array)
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

        if not self.sock:
            print("[!] Erro: Socket AF_PACKET não está aberto!")
            return
        
        sent_count = 0
        try:
            for pkt in packets:
                pkt_bytes = bytes(pkt) if not isinstance(pkt, bytes) else pkt
                self.sock.send(pkt_bytes)
                sent_count += 1
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