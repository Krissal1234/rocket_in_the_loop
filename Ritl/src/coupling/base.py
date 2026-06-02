from abc import ABC, abstractmethod
from models.sensor_data import SensorData
from adapters.base import FswAdapter


class CouplingStrategy(ABC):
    """Defines how sensor data flows from the simulator to the FSW and when
    the simulator is allowed to proceed"""

    @abstractmethod
    def on_sensor(self, sensor: SensorData, fsw: FswAdapter) -> float:
        """
            In current implementation : may block (lockstep) or return immediately (snapshot).
        """
