import logging
from coupling.base import CouplingStrategy
from models.sensor_data import SensorData
from adapters.base import FswAdapter

log = logging.getLogger("ritl.coupling.lockstep")


class LockstepCoupling(CouplingStrategy):
    """Control Lockstep: the simulator blocks after every sensor update until
    the FSW returns a fresh airbrake command.
    """

    def __init__(self, timeout: float = 0.2):
        self._timeout = timeout

    def on_sensor(self, sensor: SensorData, fsw: FswAdapter) -> float:
        fsw.send_sensor(sensor)
        dep = fsw.wait_for_airbrake(self._timeout)
        log.debug("lockstep t=%.3f dep=%.4f", sensor.t, dep)
        return dep
