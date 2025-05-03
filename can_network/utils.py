import struct

def float_to_hex_array(number, precision="float32"):
    if precision == "float32":
        packed = struct.pack(">f", number)  # Convert float to 4 bytes (big-endian)
    elif precision == "float64":
        packed = struct.pack(">d", number)  # Convert float to 8 bytes (big-endian)
    else:
        raise ValueError("Unsupported precision. Use 'float32' or 'float64'.")

    return list(packed)


def hex_array_to_float(hex_array, precision="float32"):
    byte_array = bytes(hex_array)

    if precision == "float32":
        return struct.unpack(">f", hex_array)[0]  # Convert 4 bytes to float
    elif precision == "float64":
        return struct.unpack(">d", hex_array)[0]  # Convert 8 bytes to float
    else:
        raise ValueError("Unsupported precision. Use 'float32' or 'float64'.")


def int_to_hex_array(number, size=4, signed=True):
    """Convert an integer to a hex byte array representation."""
    packed = number.to_bytes(size, byteorder="big", signed=signed)
    return list(packed)


def hex_array_to_int(hex_array, signed=True):
    """Convert a hex byte array back to an integer."""
    return int.from_bytes(hex_array, byteorder="big", signed=signed)


def bool_to_hex_array(value):
    """Convert a boolean to a hex byte array representation."""
    return [int(value)]  # Convert True → 1 (0x01), False → 0 (0x00)


def hex_array_to_bool(hex_array):
    """Convert a hex byte array back to a boolean."""
    return bool(hex_array[0])  # Convert 0x01 → True, 0x00 → False
