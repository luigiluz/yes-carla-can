import can_network.constants as consts

# The format of the communication matrix is the following:
# <signal-name> : {
#    "CAN_ID_KEY": <can-id>,
#    "PERIOD_KEY": <period-in-seg>
#}
# TODO: Specify remaining fields from DBC file such as:
# value type (integer, float, bool, ...)
# bit_length (16, 32, ...)
# bit_start (0, 4, 8, ...)

# Note: The current CAN_ID and PERIODs were chosen randomly
# The period determined here is current not implemented in the simulation

CAN_COMMUNICATION_MATRIX_DICT = {
	consts.THROTTLE_KEY: {
		consts.CAN_ID_KEY: 0x600,
		consts.PERIOD_KEY: 0.1
	},
	consts.BRAKE_KEY: {
		consts.CAN_ID_KEY: 0x601,
		consts.PERIOD_KEY: 0.01
	},
	consts.STEER_KEY: {
		consts.CAN_ID_KEY: 0x602,
		consts.PERIOD_KEY: 0.01
	},
	consts.REVERSE_KEY: {
		consts.CAN_ID_KEY: 0x603,
		consts.PERIOD_KEY: 0.01
	},
	consts.HAND_BRAKE_KEY: {
		consts.CAN_ID_KEY: 0x604,
		consts.PERIOD_KEY: 0.01
	},
	consts.AUTOPILOT_KEY: {
		consts.CAN_ID_KEY: 0x605,
		consts.PERIOD_KEY: 0.01
	},
	consts.MANUAL_TRANSMISSION_KEY: {
		consts.CAN_ID_KEY: 0x606,
		consts.PERIOD_KEY: 0.01
	},
	consts.GEAR_KEY: {
		consts.CAN_ID_KEY: 0x607,
		consts.PERIOD_KEY: 0.01
	},
	consts.LIGHT_TYPE_KEY: {
		consts.CAN_ID_KEY: 0x608,
		consts.PERIOD_KEY: 0.01
	},
	consts.HIGH_BEAM_KEY: {
		consts.CAN_ID_KEY: 0x609,
		consts.PERIOD_KEY: 0.01
	},
	consts.BLINKER_KEY: {
		consts.CAN_ID_KEY: 0x60A,
		consts.PERIOD_KEY: 0.01
	},
	consts.INTERIOR_LIGHT_KEY: {
		consts.CAN_ID_KEY: 0x60B,
		consts.PERIOD_KEY: 0.01
	},
	consts.DOORS_KEY: {
		consts.CAN_ID_KEY: 0x60C,
		consts.PERIOD_KEY: 0.01
	},
}
