

import queue
import threading
from ai_pipeline.receiver import start_avtp_listener
from ai_pipeline.ai_agent import run_inference_loop
from ai_pipeline.actuator import execute_control


if __name__ == "__main__":
    # Fila de tamanho 1 para priorizar frames em tempo real
    frame_queue = queue.Queue(maxsize=1)

    t_producer = threading.Thread(
        target=start_avtp_listener, 
        args=(frame_queue,), 
        daemon=True
    )
    t_consumer = threading.Thread(
        target=run_inference_loop, 
        args=(frame_queue, execute_control), 
        daemon=True
    )

    t_producer.start()
    t_consumer.start()

    t_producer.join()
    t_consumer.join()
