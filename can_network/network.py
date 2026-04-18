import can
import carla

from can_network.dbc import load_and_validate, REQUIRED_SIGNALS


class CAN_Network(object):
    door_change_state = False
    current_lights = carla.VehicleLightState.NONE

    def __init__(self, dbc_path="data/carla.dbc"):
        self.bus = can.ThreadSafeBus(
            interface="socketcan", channel="vcan0", receive_own_messages=True
        )
        self.recvd_controls = carla.VehicleControl()
        self.db, self.cycle_times = load_and_validate(dbc_path)

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _build_msg(self, message_name, value) -> can.Message:
        """Encode a single-signal CAN message from the DBC and return a can.Message ready to send."""
        try:
            dbc_msg = self.db.get_message_by_name(message_name)
        except KeyError:
            available = [m.name for m in self.db.messages]
            raise RuntimeError(
                f"[CAN] Message '{message_name}' not found in DBC. "
                f"Available: {available}"
            ) from None
        signal_name = REQUIRED_SIGNALS[message_name]
        return can.Message(
            arbitration_id=dbc_msg.frame_id,
            data=dbc_msg.encode({signal_name: value}),
            is_extended_id=dbc_msg.is_extended_frame,
        )

    # ------------------------------------------------------------------
    # Senders
    # ------------------------------------------------------------------

    def send_switch_door_state_msg(self):
        self.bus.send(self._build_msg("DOORS", True))

    def send_current_lights_msg(self, lights):
        # VehicleLightState values above 0xFF are carla-only and not in the DBC;
        # mask them out before encoding.
        self.bus.send(self._build_msg("GENERAL_LIGHTS", int(lights) & 0xFF))

    def send_throttle_msg(self, controls):
        self.bus.send(self._build_msg("THROTTLE", int(controls.throttle * 255)))

    def send_steer_msg(self, controls):
        self.bus.send(self._build_msg("STEER", int((controls.steer + 1) / 2 * 255)))

    def send_brake_msg(self, controls):
        self.bus.send(self._build_msg("BRAKE", int(controls.brake * 255)))

    def send_hand_brake_msg(self, controls):
        self.bus.send(self._build_msg("HAND_BRAKE", int(controls.hand_brake)))

    def send_reverse_msg(self, controls):
        self.bus.send(self._build_msg("REVERSE", int(controls.reverse)))

    def send_manual_transmission_msg(self, controls):
        self.bus.send(self._build_msg("MANUAL_TRANSMISSION", int(controls.manual_gear_shift)))

    def send_gear_msg(self, controls):
        self.bus.send(self._build_msg("GEAR", int(controls.gear)))

    def send_autopilot_msg(self, controls):
        # controls.autopilot is not a standard VehicleControl field;
        # adapt the value source here if you have an autopilot state elsewhere.
        pass

    def send_msg(self, controls):
        """Convenience method — sends all messages at once (bypasses per-message timing)."""
        self.send_throttle_msg(controls)
        self.send_steer_msg(controls)
        self.send_brake_msg(controls)
        self.send_hand_brake_msg(controls)
        self.send_reverse_msg(controls)
        self.send_manual_transmission_msg(controls)
        self.send_gear_msg(controls)

    # ------------------------------------------------------------------
    # Receivers
    # ------------------------------------------------------------------

    def recv_switch_door_state_msg(self):
        self.door_change_state = not self.door_change_state
        return self.door_change_state

    def recv_msg(self):
        try:
            recv_msg = self.bus.recv(timeout=0)
        except can.CanOperationError:
            return self.recvd_controls
        while recv_msg is not None:
            data = self.db.decode_message(recv_msg.arbitration_id, recv_msg.data)

            try:
                dbc_msg = self.db.get_message_by_frame_id(recv_msg.arbitration_id)
            except KeyError:
                print(f"[CAN] INFO: Received unknown arbitration_id 0x{recv_msg.arbitration_id:X}, skipping")
                recv_msg = self.bus.recv(timeout=0)
                continue

            name = dbc_msg.name

            if name == "THROTTLE":
                self.recvd_controls.throttle = data[REQUIRED_SIGNALS["THROTTLE"]] / 255.0

            elif name == "STEER":
                self.recvd_controls.steer = (data[REQUIRED_SIGNALS["STEER"]] / 255.0) * 2 - 1

            elif name == "BRAKE":
                self.recvd_controls.brake = data[REQUIRED_SIGNALS["BRAKE"]] / 255.0

            elif name == "HAND_BRAKE":
                self.recvd_controls.hand_brake = bool(data[REQUIRED_SIGNALS["HAND_BRAKE"]])

            elif name == "REVERSE":
                self.recvd_controls.reverse = bool(data[REQUIRED_SIGNALS["REVERSE"]])

            elif name == "MANUAL_TRANSMISSION":
                self.recvd_controls.manual_gear_shift = bool(data[REQUIRED_SIGNALS["MANUAL_TRANSMISSION"]])

            elif name == "GEAR":
                self.recvd_controls.gear = int(data[REQUIRED_SIGNALS["GEAR"]])

            elif name == "DOORS":
                if data[REQUIRED_SIGNALS["DOORS"]]:
                    print(data)
                    self.door_change_state = True

            elif name == "GENERAL_LIGHTS":
                self.current_lights = carla.VehicleLightState(
                    int(data[REQUIRED_SIGNALS["GENERAL_LIGHTS"]])
                )

            try:
                recv_msg = self.bus.recv(timeout=0)
            except can.CanOperationError:
                break

        return self.recvd_controls
