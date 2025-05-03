from queue import Queue
import threading

import can
from can_network.listener import CANListener


class CANBus(object):
    def __init__(self):
        self._listeners = []
        self._queue = Queue()

        threading.Thread(target=self._bus_worker, daemon=True).start()
        threading.Thread(target=self._notifier_worker, daemon=True).start()

    def subscribe(self, listener: CANListener) -> None:
        self._listeners.append(listener)

    def unsubscribe(self, listener: CANListener) -> None:
        self._listeners.remove(listener)

    def _bus_worker(self):
        bus = can.interface.Bus(channel='vcan0', interface='socketcan', receive_own_messages=True)
        while True:
            recv = bus.recv(timeout=None)
            self._queue.put_nowait(recv)

    def _notifier_worker(self):
        while True:
            event = self._queue.get()
            for listener in self._listeners:
                listener.notify(event)