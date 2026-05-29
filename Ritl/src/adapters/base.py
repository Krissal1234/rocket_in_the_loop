from abc import ABC, abstractmethod
from models.sensor_data import SensorData


class FswAdapter(ABC):
    """Interface for any flight software backend"""

    @abstractmethod
    def start(self) -> None:
        """Establish connection. Blocks until ready."""

    @abstractmethod
    def send_sensor(self, data: SensorData) -> bool:
        """sends one sensor sample to the FSW. Returns True on success."""

    @abstractmethod
    def get_snapshot(self) -> dict:
        """Return the latest known actuation states without blocking """

    @abstractmethod
    def wait_for_airbrake(self, timeout: float = 0.2) -> float:
        """Block until the FSW issues a fresh airbrake command"""

    @abstractmethod
    def stop(self) -> None:
        """Tear down"""

