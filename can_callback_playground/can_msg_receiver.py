import can
import time

class MyListener(can.Listener):
    def on_message_received(self, msg):
        print(f"Message received: {msg}")

def main():
    listener = MyListener()
    while True:
        with can.Bus(channel='vcan0', interface='socketcan') as bus:
            msg = bus.recv(timeout=1.0)
            if msg:
                listener.on_message_received(msg)
            else:
                print("No message received within timeout.")


if __name__ == "__main__":
    main()
