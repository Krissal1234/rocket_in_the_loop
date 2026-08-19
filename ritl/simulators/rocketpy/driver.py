import time
import numpy as np
from ritl.bridge.client import BridgeClient
from ritl.models.sensor_data import SensorData
from ritl.simulators.base import SimulationResult, SimulatorDriver
from ritl.simulators.rocketpy.controllers.non_sil import NonSilControllers
from ritl.simulators.rocketpy.controllers.sil import SilController
from ritl.simulators.rocketpy.rockets import calisto, cameos

ROCKETS = {
    "calisto": calisto.build,
    "cameos":  cameos.build,
}

class RocketPyDriver(SimulatorDriver):
    def __init__(self, is_sil: bool, rocket: str):
        self._is_sil= is_sil
        self._rocket = rocket

    def run(self, bridge_client: BridgeClient) -> SimulationResult:
        if bridge_client:
          bridge_client.connect()
          self._bridge = bridge_client
          self._ctrl = SilController(self._bridge)
        else:
          self._ctrl = NonSilControllers()

        start = time.time()
        flight = ROCKETS[self._rocket](self._ctrl)
        wall_time = time.time() - start

        if bridge_client:
          bridge_client.close()

        return self._to_result(flight, wall_time)

    def _to_result(self, flight, wall_time: float) -> SimulationResult:
        drogue_time = main_time = None
        for t, chute in flight.parachute_events:
            if "drogue" in chute.name.lower() and drogue_time is None:
                drogue_time = t
            if "main" in chute.name.lower() and main_time is None:
                main_time = t

        alt = np.array(flight.z.source)
        vz = np.array(flight.vz.source)
        ground = flight.env.elevation

        return SimulationResult(
            t=alt[:, 0],
            altitude=alt[:, 1] - ground,
            vz=vz[:, 1],
            apogee=flight.apogee - ground,
            apogee_time=flight.apogee_time,
            drogue_time=drogue_time,
            main_time=main_time,
            wall_time_s=wall_time,
        )