import random
import logging

from numpy import copy
from models.sensor_data import SensorData

log = logging.getLogger("ritl.fault_injection")


class FaultInjector:
    """
    Fault injection on incoming sensor data from simulator.
    """

    def __init__(self, freeze_baro: bool = False, freeze_baro_at: float = 0.0, dropout_rate: float = 0.0):
        log.info("FaultInjector init: freeze_baro=%s freeze_baro_at=%s", freeze_baro, freeze_baro_at)
        self.dropout_rate = dropout_rate
        self.freeze_baro = freeze_baro
        self.freeze_baro_at = freeze_baro_at
        self._frozen_value = None
        self._dropped = 0
        self._total = 0

    def process(self, sensor: SensorData) -> SensorData | None:
        self._total += 1
        if self.dropout_rate > 0 and random.random() < self.dropout_rate:
            self._dropped += 1
            return None

        if self.freeze_baro:
            if self._frozen_value is None and sensor.t is not None and sensor.t >= self.freeze_baro_at:
                if sensor.baro is not None and isinstance(sensor.baro, float):
                    self._frozen_value = sensor.baro
                    log.warning("Baro frozen at t=%.2fs, value=%.2f Pa", sensor.t, self._frozen_value)
            if self._frozen_value is not None:
                sensor.baro = self._frozen_value

        return sensor

    def stats(self) -> dict:
        return {
            "total_packets": self._total,
            "dropped_packets": self._dropped,
            "dropout_rate_actual": self._dropped / max(self._total, 1),
        }


def no_faults() -> FaultInjector:
    return FaultInjector()

def frozen_baro() -> FaultInjector:
    return FaultInjector(freeze_baro=True)