FEATURE_CAN_ID_PAYLOAD_MAPPER = {
    "hand_brake": {
        "id": 0x604,
        "payload": [0x01]
    },
    "doors": {
        "id": 0x60C,
        "payload": [0x01]
    },
    "reverse": {
        "id": 0x607,
        "payload": [0xFF, 0xFF, 0xFF, 0xFF]
    },
    "high_beam": {
        "id": 0x60D,
        "payload": [0x00, 0x00, 0x00, 0x04]
    },
    "internal_lights": {
        "id": 0x60D,
        "payload": [0x00, 0x00, 0x01, 0x00]
    },
    "low_beam": {
        "id": 0x60D,
        "payload": [0x00, 0x00, 0x00, 0x01]
    },
    "fog_lights": {
        "id": 0x60D,
        "payload": [0x00, 0x00, 0x00, 0x03]
    },
    "lights_off": {
        "id": 0x60D,
        "payload": [0x00, 0x00, 0x00, 0x83]
    },
    "position_lights": {
        "id": 0x60D,
        "payload": [0x00, 0x00, 0x00, 0x00]
    },
    "left_blink": {
        "id": 0x60D,
        "payload": [0x00, 0x00, 0x00, 0x20]
    },
    "right_blink": {
        "id": 0x60D,
        "payload": [0x00, 0x00, 0x00, 0x10]
    },
}
