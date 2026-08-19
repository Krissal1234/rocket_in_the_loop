import logging
from ritl.coupling.base import CouplingStrategy
from ritl.models.actuation_data import ActuationData
from ritl.models.sensor_data import SensorData
from ritl.adapters.base import FswAdapter

log = logging.getLogger("ritl.coupling.blocking")


class BlockingCoupling(CouplingStrategy):
    """BlockingCoupling: the simulator blocks after every sensor update until
    the FSW returns a fresh airbrake command.
    """

    def __init__(self, timeout: float = 0.2):
        self._timeout = timeout

    def on_sensor(self, sensor: SensorData, fsw: FswAdapter) -> ActuationData:
        fsw.send_sensor(sensor)
        actuation_state = fsw.wait_for_actuation(self._timeout)
        return actuation_state
