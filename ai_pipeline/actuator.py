from can_network.network import CAN_Network 
import carla

can_net = CAN_Network()
manual_override_blocked = False

def execute_control(command):
    global manual_override_blocked
    
    control = carla.VehicleControl()

    if command == "FORWARD" and not manual_override_blocked:
        control.throttle = 0.7  # 50% de acelerador
        control.brake = 0.0
    elif command == "STOP":
        control.throttle = 0.0
        control.brake = 1.0     # 80% de freio
        manual_override_blocked = True 

    if command == "FORWARD":
        manual_override_blocked = False

    # Envia o comando estruturado via barramento CAN para o simulador
    can_net.send_msg(control)
