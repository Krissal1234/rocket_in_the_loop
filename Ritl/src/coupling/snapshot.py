import logging
from coupling.base import CouplingStrategy
from models.sensor_data import SensorData
from adapters.base import FswAdapter

log = logging.getLogger("ritl.coupling.snapshot")


class SnapshotCoupling(CouplingStrategy):
    """Snapshot: sensor data is forwarded to the FSW but the simulator
    does not wait for a response. The latest known actuation state is returned immediately from a snapshot from the flagstore
    """

    def on_sensor(self, sensor: SensorData, fsw: FswAdapter) -> float:
        fsw.send_sensor(sensor)
        dep = fsw.get_snapshot()["airbrake_dep_level"]
        log.debug("snapshot t=%.3f dep=%.4f", sensor.t, dep)
        return dep

