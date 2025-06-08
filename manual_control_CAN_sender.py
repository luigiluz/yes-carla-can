import can
import time
import carla

import can_network

from gui import keyboard_control

try:
    import pygame
    from pygame.locals import KMOD_CTRL
    from pygame.locals import KMOD_SHIFT
    from pygame.locals import K_0
    from pygame.locals import K_9
    from pygame.locals import K_BACKQUOTE
    from pygame.locals import K_BACKSPACE
    from pygame.locals import K_COMMA
    from pygame.locals import K_DOWN
    from pygame.locals import K_ESCAPE
    from pygame.locals import K_F1
    from pygame.locals import K_LEFT
    from pygame.locals import K_PERIOD
    from pygame.locals import K_RIGHT
    from pygame.locals import K_SLASH
    from pygame.locals import K_SPACE
    from pygame.locals import K_TAB
    from pygame.locals import K_UP
    from pygame.locals import K_a
    from pygame.locals import K_b
    from pygame.locals import K_c
    from pygame.locals import K_d
    from pygame.locals import K_f
    from pygame.locals import K_g
    from pygame.locals import K_h
    from pygame.locals import K_i
    from pygame.locals import K_l
    from pygame.locals import K_m
    from pygame.locals import K_n
    from pygame.locals import K_o
    from pygame.locals import K_p
    from pygame.locals import K_q
    from pygame.locals import K_r
    from pygame.locals import K_s
    from pygame.locals import K_t
    from pygame.locals import K_v
    from pygame.locals import K_w
    from pygame.locals import K_x
    from pygame.locals import K_z
    from pygame.locals import K_MINUS
    from pygame.locals import K_EQUALS
except ImportError:
    raise RuntimeError('cannot import pygame, make sure pygame package is installed')

class KeyboardSenderControl(object):
    """Class that handles keyboard input."""
    def __init__(self, can_network, start_in_autopilot = False):
        #self._can = can_network
        self._autopilot_enabled = start_in_autopilot
        self._ackermann_enabled = False
        self._ackermann_reverse = 1

        self._control = carla.VehicleControl()
        self._ackermann_control = carla.VehicleAckermannControl()
        self._lights = carla.VehicleLightState.NONE

        self._steer_cache = 0.0

    def _parse_vehicle_keys(self, keys, milliseconds):
        if keys[K_UP] or keys[K_w]:
            if not self._ackermann_enabled:
                self._control.throttle = min(self._control.throttle + 0.1, 1.00)
            else:
                self._ackermann_control.speed += round(milliseconds * 0.005, 2) * self._ackermann_reverse
        else:
            if not self._ackermann_enabled:
                self._control.throttle = 0.0

        if keys[K_DOWN] or keys[K_s]:
            if not self._ackermann_enabled:
                self._control.brake = min(self._control.brake + 0.2, 1)
            else:
                self._ackermann_control.speed -= min(abs(self._ackermann_control.speed), round(milliseconds * 0.005, 2)) * self._ackermann_reverse
                self._ackermann_control.speed = max(0, abs(self._ackermann_control.speed)) * self._ackermann_reverse
        else:
            if not self._ackermann_enabled:
                self._control.brake = 0

        steer_increment = 5e-4 * milliseconds
        if keys[K_LEFT] or keys[K_a]:
            if self._steer_cache > 0:
                self._steer_cache = 0
            else:
                self._steer_cache -= steer_increment
        elif keys[K_RIGHT] or keys[K_d]:
            if self._steer_cache < 0:
                self._steer_cache = 0
            else:
                self._steer_cache += steer_increment
        else:
            self._steer_cache = 0.0
        self._steer_cache = min(0.7, max(-0.7, self._steer_cache))
        if not self._ackermann_enabled:
            self._control.steer = round(self._steer_cache, 1)
            self._control.hand_brake = keys[K_SPACE]
        else:
            self._ackermann_control.steer = round(self._steer_cache, 1)

    def parse_events(self, clock, can_network):
        current_lights = self._lights
        self._parse_vehicle_keys(pygame.key.get_pressed(), clock.get_time())
        self._control.reverse = self._control.gear < 0
        # Set automatic control-related vehicle lights
        if self._control.brake:
            current_lights |= carla.VehicleLightState.Brake
        else: # Remove the Brake flag
            current_lights &= ~carla.VehicleLightState.Brake
        if self._control.reverse:
            current_lights |= carla.VehicleLightState.Reverse
        else: # Remove the Reverse flag
            current_lights &= ~carla.VehicleLightState.Reverse
        if current_lights != self._lights: # Change the light state only if necessary
            self._lights = current_lights
            # As "lights"precisam ser enviadas e recebidas aqui em cima
            # Elas vem tudo num pacotão que é uma mensagem unica
            #world.player.set_light_state(carla.VehicleLightState(self._lights))

        #self._can.send_msg(self._control)
        can_network.send_msg(self._control)

    @staticmethod
    def _is_quit_shortcut(key):
        return (key == K_ESCAPE) or (key == K_q and pygame.key.get_mods() & KMOD_CTRL)

def keyboard_parser_loop():
    print("Starting keyboard parser loop")
    pygame.init()
    pygame.font.init()

    screen = pygame.display.set_mode((640, 480))
    can_net = can_network.CAN_Network()
    controller = KeyboardSenderControl(can_net)
    clock = pygame.time.Clock()
    running = True

    while running:
        # Essas daqui pra baixo ficam dentro do parse_events no original
        # Se funcionar, depois mover pra lá
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYUP:
                if controller._is_quit_shortcut(event.key):
                    return True
                elif event.key == K_o:
                    try:
                        can_net.send_switch_door_state_msg()
                    except:
                        pass

        clock.tick_busy_loop(60)
        #print(f"{pygame.key.get_pressed()})")
        controller.parse_events(clock, can_net)
        pygame.display.flip()

def main():
    print("Sending commands through CAN bus")
    #can_net = can_network.CAN_Network()

    #control = carla.VehicleControl()
    #control = None # FIXME: Preciso pegar isso no formato correto a partir das teclas do teclado
    #can_net.send_msg(control)

    # O que eu preciso aqui é:
    # Pegar as teclas pressionadas e enviar os comandos correspondentes pelo barramento CAN

    try:
        keyboard_parser_loop()
    except KeyboardInterrupt:
        print('\nCancelled by user. Bye!')
        pygame.quit()

if __name__ == "__main__":
    main()
    # TODO: Fazer leitura dos comandos do teclado
    # Enviar pel barramento CAN
