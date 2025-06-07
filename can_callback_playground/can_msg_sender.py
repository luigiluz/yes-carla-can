import can
import time

def main():
    print("Sending can menssages")

    bus = can.interface.Bus(channel='vcan0', bustype='socketcan')

    while True:
        msg = can.Message(arbitration_id=0x123, data=[0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08], is_extended_id=False)
        try:
            bus.send(msg)
            time.sleep(0.5)  # Sleep for a short duration to avoid flooding the bus
            print(f"Message sent: {msg}")
        except can.CanError:
            print("Message NOT sent")
        except KeyboardInterrupt:
            print("Exiting...")
            break
        except Exception as e:  # Catch all other exceptions
            print(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
