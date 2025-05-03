import can 
from can_network.comm_matrix import (
    CAN_COMMUNICATION_MATRIX_DICT,
)
import can_network.constants as consts
import can_network.utils as utils
import carla

class CAN_Network(object):

    def __init__(self):
        self.bus = can.interface.Bus(channel='vcan0', interface='socketcan', receive_own_messages=True)
        self.recvd_controls = carla.VehicleControl()

    # As variaveis que vem de controls podem ser encontradas aqui:
    # https://carla.readthedocs.io/en/latest/python_api/#carlavehiclecontrol
    def send_msg(self, controls):
        # Throttle msg (float)
        msg_data = utils.float_to_hex_array(controls.throttle)
        msg = can.Message(arbitration_id=CAN_COMMUNICATION_MATRIX_DICT[consts.THROTTLE_KEY][consts.CAN_ID_KEY], data=msg_data, is_extended_id=False)
        self.bus.send(msg)

        # Steer msg (float)
        msg_data = utils.float_to_hex_array(controls.steer)
        msg = can.Message(arbitration_id=CAN_COMMUNICATION_MATRIX_DICT[consts.STEER_KEY][consts.CAN_ID_KEY], data=msg_data, is_extended_id=False)
        self.bus.send(msg)

        # Brake msg (float)
        msg_data = utils.float_to_hex_array(controls.brake)
        msg = can.Message(arbitration_id=CAN_COMMUNICATION_MATRIX_DICT[consts.BRAKE_KEY][consts.CAN_ID_KEY], data=msg_data, is_extended_id=False)
        self.bus.send(msg)

        # Hand brake msg (bool)
        msg_data = utils.bool_to_hex_array(controls.hand_brake)
        msg = can.Message(arbitration_id=CAN_COMMUNICATION_MATRIX_DICT[consts.HAND_BRAKE_KEY][consts.CAN_ID_KEY], data=msg_data, is_extended_id=False)
        self.bus.send(msg)

        # Reverse msg (bool)
        msg_data = utils.bool_to_hex_array(controls.reverse)
        msg = can.Message(arbitration_id=CAN_COMMUNICATION_MATRIX_DICT[consts.REVERSE_KEY][consts.CAN_ID_KEY], data=msg_data, is_extended_id=False)
        self.bus.send(msg)

        # Manual gear shift msg (bool)
        msg_data = utils.bool_to_hex_array(controls.manual_gear_shift)
        msg = can.Message(arbitration_id=CAN_COMMUNICATION_MATRIX_DICT[consts.MANUAL_TRANSMISSION_KEY][consts.CAN_ID_KEY], data=msg_data, is_extended_id=False)
        self.bus.send(msg)

        # Gear msg (int)
        msg_data = utils.int_to_hex_array(controls.gear)
        msg = can.Message(arbitration_id=CAN_COMMUNICATION_MATRIX_DICT[consts.GEAR_KEY][consts.CAN_ID_KEY], data=msg_data, is_extended_id=False)
        self.bus.send(msg)


    def recv_msg(self):
        recv_msg = self.bus.recv(timeout=0)
        while recv_msg is not None:
            if recv_msg.arbitration_id == CAN_COMMUNICATION_MATRIX_DICT[consts.THROTTLE_KEY][consts.CAN_ID_KEY]:
                self.recvd_controls.throttle = utils.hex_array_to_float(recv_msg.data)

            elif recv_msg.arbitration_id == CAN_COMMUNICATION_MATRIX_DICT[consts.STEER_KEY][consts.CAN_ID_KEY]:
                self.recvd_controls.steer = utils.hex_array_to_float(recv_msg.data)

            elif recv_msg.arbitration_id == CAN_COMMUNICATION_MATRIX_DICT[consts.BRAKE_KEY][consts.CAN_ID_KEY]:
                self.recvd_controls.brake = utils.hex_array_to_float(recv_msg.data)

            elif recv_msg.arbitration_id == CAN_COMMUNICATION_MATRIX_DICT[consts.HAND_BRAKE_KEY][consts.CAN_ID_KEY]:
                self.recvd_controls.hand_brake = utils.hex_array_to_bool(recv_msg.data)

            elif recv_msg.arbitration_id == CAN_COMMUNICATION_MATRIX_DICT[consts.REVERSE_KEY][consts.CAN_ID_KEY]:
                self.recvd_controls.reverse = utils.hex_array_to_bool(recv_msg.data)

            elif recv_msg.arbitration_id == CAN_COMMUNICATION_MATRIX_DICT[consts.MANUAL_TRANSMISSION_KEY][consts.CAN_ID_KEY]:
                self.recvd_controls.manual_gear_shift = utils.hex_array_to_bool(recv_msg.data)

            elif recv_msg.arbitration_id == CAN_COMMUNICATION_MATRIX_DICT[consts.GEAR_KEY][consts.CAN_ID_KEY]:
                self.recvd_controls.gear = utils.hex_array_to_int(recv_msg.data)
            recv_msg = self.bus.recv(timeout=0)

        return self.recvd_controls

