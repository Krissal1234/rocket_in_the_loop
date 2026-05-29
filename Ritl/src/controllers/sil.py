import logging
import zmq
from models.sensor_data import SensorData

log = logging.getLogger("ritl.controllers.sil")

_ZMQ_TIMEOUT_MS = 8000

class SilController:
    """RocketPy controller that forwards sensor data to a SimBridge`
    over ZMQ and applies the returned actuation commands.

    This is the RocketPy-specific adapter for the simulator side"""

    def __init__(self, zmq_address: str):
        self._address = zmq_address
        self._socket: zmq.Socket | None = None
        self._last_time: float | None = None

    def connect(self) -> None:
        ctx = zmq.Context.instance()
        self._socket = ctx.socket(zmq.REQ)
        self._socket.setsockopt(zmq.RCVTIMEO, _ZMQ_TIMEOUT_MS)
        self._socket.connect(self._address)
        log.info("SilController connected to SimBridge at %s", self._address)

    def close(self) -> None:
        if self._socket:
            self._socket.close()
            self._socket = None

    # --- RocketPy controller interface ---
    def drogue_trigger(self, pressure, height, state) -> bool:
        resp = self._send({"type": "DROGUE_POLL"})
        return bool(resp.get("drogue", False))

    def main_trigger(self, pressure, height, state) -> bool:
        resp = self._send({"type": "MAIN_POLL"})
        return bool(resp.get("main", False))

    def airbrake_controller(
        self, time, sampling_rate, state_vector, state_history,
        observed_variables, air_brakes, sensors, environment,
    ):
        # RocketPy calls each controller twice per ODE step with the same timestamp at the current version
        if time == self._last_time:
            return time
        self._last_time = time

        accel = sensors[0].measurement
        baro  = sensors[1].measurement
        gyro  = sensors[2].measurement

        sensor = SensorData(
            t       = float(time),
            accel_x = float(accel[0]),
            accel_y = float(accel[1]),
            accel_z = float(accel[2]),
            baro    = float(baro),
            gyro_x  = float(gyro[0]),
            gyro_y  = float(gyro[1]),
            gyro_z  = float(gyro[2]),
        )

        resp = self._send({"type": "SENSOR", **sensor.to_dict()})
        dep_level = float(resp.get("airbrake_dep_level", 0.0))

        if dep_level > 0 or air_brakes.deployment_level > 0:
            log.info("DEP %.4f %.6f", time, dep_level)

        air_brakes.deployment_level = dep_level
        return time

    def _send(self, data: dict) -> dict:
        self._socket.send_json(data)
        return self._socket.recv_json()
