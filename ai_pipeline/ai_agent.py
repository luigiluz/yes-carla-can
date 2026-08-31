import torch

def run_inference_loop(frame_queue, control_callback):
    # Exemplo com modelo leve (YOLOv8 nano) pré-treinado
    model = torch.hub.load('ultralytics/yolov5', 'yolov5n', pretrained=True)
    
    while True:
        # Aguarda até que o produtor insira um frame recente
        frame = frame_queue.get() 
        
        results = model(frame)
        
        # Regra de decisão simplificada: verifica se há carros/pessoas na zona central
        has_obstacle = parse_detections(results)

        if has_obstacle:
            control_callback(command="STOP")
        else:
            control_callback(command="FORWARD")

def parse_detections(results):
    # Lógica de corte (ROI) na frente do veículo para verificar colisão
    # Retorna True se houver objeto detectado no caminho frontal
    return False
