from abc import ABC, abstractmethod
import can


class CANListener(ABC):
    @abstractmethod
    def notify(self, event: can.Message) -> None:
        pass