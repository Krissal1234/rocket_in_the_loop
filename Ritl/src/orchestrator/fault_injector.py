import random
import logging
from models.sensor_data import SensorData

log = logging.getLogger("ritl.fault")

class FaultInjector:
    """
    dropout_rate: probability [0,1] of dropping a sensor packet
    """
    def __init__(self, dropout_rate: float = 0.0,):
        self.dropout_rate = dropout_rate
        self._dropped = 0
        self._total = 0

    def process(self, sensor: SensorData) -> SensorData | None:
        self._total += 1

        if self.dropout_rate > 0 and random.random() < self.dropout_rate:
            self._dropped += 1
            log.debug("FAULT dropped packet t=%.3f", sensor.t)
            return None

        return sensor

    def stats(self) -> dict:
        return {
            "total_packets": self._total,
            "dropped_packets": self._dropped,
            "dropout_rate_actual": self._dropped / max(self._total, 1),
        }

def no_faults() -> FaultInjector:
    return FaultInjector()