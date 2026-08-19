import logging
from ritl.coupling.base import CouplingStrategy
from ritl.models.actuation_data import ActuationData
from ritl.models.sensor_data import SensorData
from ritl.adapters.base import FswAdapter

log = logging.getLogger("ritl.coupling.non_blocking")


class NonBlockingCoupling(CouplingStrategy):
    """NonBlocking: sensor data is forwarded to the FSW but the simulator
    does not wait for a response. The latest known actuation state is returned immediately from a snapshot from the flagstore
    """

    def on_sensor(self, sensor: SensorData, fsw: FswAdapter) -> ActuationData:
        fsw.send_sensor(sensor)
        actuation_state = fsw.get_snapshot()
        return actuation_state

