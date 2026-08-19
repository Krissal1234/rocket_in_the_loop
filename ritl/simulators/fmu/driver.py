
from ritl.simulators.base import SimulatorDriver


class FmuDriver(SimulatorDriver):
    def __init__(self, rocket: str):
        self._rocket = rocket
        self._last_time = None