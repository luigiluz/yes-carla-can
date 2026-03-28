import can
import cantools
import carla


class CAN_Network(object):
    door_change_state = False
    current_lights = carla.VehicleLightState.NONE

    def __init__(self):
        self.bus = can.ThreadSafeBus(
            interface="socketcan", channel="vcan0", receive_own_messages=True
        )
        self.recvd_controls = carla.VehicleControl()
        self.db = cantools.database.load_file("data/carla.dbc")

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _build_msg(self, message_name, signal_values: dict) -> can.Message:
        """Encode a CAN message from the DBC and return a can.Message ready to send."""
        dbc_msg = self.db.get_message_by_name(message_name)
        return can.Message(
            arbitration_id=dbc_msg.frame_id,
            data=dbc_msg.encode(signal_values),
            is_extended_id=dbc_msg.is_extended_frame,
        )

    # ------------------------------------------------------------------
    # Senders
    # ------------------------------------------------------------------

    def send_switch_door_state_msg(self):
        self.bus.send(self._build_msg("DOORS", {"DOORS_signal": True}))

    def send_current_lights_msg(self, lights):
        # GENERAL_LIGHTS_signal is 8-bit (0-255). VehicleLightState values above
        # 0xFF (Interior=256, Special1=512) are carla-only and not in the DBC,
        # so mask them out before encoding.
        value = int(lights) & 0xFF
        self.bus.send(
            self._build_msg("GENERAL_LIGHTS", {"GENERAL_LIGHTS_signal": value})
        )

    def send_throttle_msg(self, controls):
        self.bus.send(
            self._build_msg(
                "THROTTLE", {"THROTTLE_signal": int(controls.throttle * 255)}
            )
        )

    def send_steer_msg(self, controls):
        self.bus.send(
            self._build_msg(
                "STEER", {"STEER_signal": int((controls.steer + 1) / 2 * 255)}
            )
        )

    def send_brake_msg(self, controls):
        self.bus.send(
            self._build_msg("BRAKE", {"BRAKE_signal": int(controls.brake * 255)})
        )

    def send_hand_brake_msg(self, controls):
        self.bus.send(
            self._build_msg(
                "HAND_BRAKE", {"HAND_BRAKE_signal": int(controls.hand_brake)}
            )
        )

    def send_reverse_msg(self, controls):
        self.bus.send(
            self._build_msg("REVERSE", {"REVERSE_signal": int(controls.reverse)})
        )

    def send_manual_transmission_msg(self, controls):
        self.bus.send(
            self._build_msg(
                "MANUAL_TRANSMISSION",
                {"MANUAL_TRANSMISSION_signal": int(controls.manual_gear_shift)},
            )
        )

    def send_gear_msg(self, controls):
        self.bus.send(self._build_msg("GEAR", {"GEAR_signal": int(controls.gear)}))

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
                recv_msg = self.bus.recv(timeout=0)
                continue

            name = dbc_msg.name

            if name == "THROTTLE":
                self.recvd_controls.throttle = data["THROTTLE_signal"] / 255.0

            elif name == "STEER":
                self.recvd_controls.steer = (data["STEER_signal"] / 255.0) * 2 - 1

            elif name == "BRAKE":
                self.recvd_controls.brake = data["BRAKE_signal"] / 255.0

            elif name == "HAND_BRAKE":
                self.recvd_controls.hand_brake = bool(data["HAND_BRAKE_signal"])

            elif name == "REVERSE":
                self.recvd_controls.reverse = bool(data["REVERSE_signal"])

            elif name == "MANUAL_TRANSMISSION":
                self.recvd_controls.manual_gear_shift = bool(
                    data["MANUAL_TRANSMISSION_signal"]
                )

            elif name == "GEAR":
                self.recvd_controls.gear = int(data["GEAR_signal"])

            elif name == "DOORS":
                if data["DOORS_signal"]:
                    print(data)
                    self.door_change_state = True

            elif name == "GENERAL_LIGHTS":
                self.current_lights = carla.VehicleLightState(
                    int(data["GENERAL_LIGHTS_signal"])
                )

            try:
                recv_msg = self.bus.recv(timeout=0)
            except can.CanOperationError:
                break

        return self.recvd_controls
