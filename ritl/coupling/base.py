from abc import ABC, abstractmethod
from ritl.models.actuation_data import ActuationData
from ritl.models.sensor_data import SensorData
from ritl.adapters.base import FswAdapter


class CouplingStrategy(ABC):
    """Defines how sensor data flows from the simulator to the FSW and when
    the simulator is allowed to proceed"""

    @abstractmethod
    def on_sensor(self, sensor: SensorData, fsw: FswAdapter) -> ActuationData:
        """
            In current implementation : may block (blocking) or return immediately (non blocking).
        """
