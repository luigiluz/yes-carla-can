import cv2
import numpy as np

def start_avtp_listener(frame_queue):
    # Lógica de socket L2 / AF_PACKET existente no seu repositório
    while True:
        raw_bytes = get_avtp_payload()  # Sua função atual de captura/reassembly
        
        # Converte bytes brutos em ndarray (zero-copy) e decodifica para BGR
        np_arr = np.frombuffer(raw_bytes, dtype=np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is not None:
            # Padrão Dropping-Queue: Descarta o frame antigo se a IA estiver ocupada
            if frame_queue.full():
                try:
                    frame_queue.get_nowait()
                except:
                    pass
            frame_queue.put(frame)
