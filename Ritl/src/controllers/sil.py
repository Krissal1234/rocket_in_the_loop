import logging
import zmq
from models.sensor_data import SensorData

log = logging.getLogger("ritl.controllers.sil")


class SilControllers:
    """ZMQ proxy: serialises RocketPy sensor state and returns FSW decisions."""

    def __init__(self, ctx: zmq.Context, zmq_address: str):
        self._ctx     = ctx
        self._address = zmq_address
        self._socket    = None
        self._last_time = None

    def connect(self):
        self._socket = self._ctx.socket(zmq.REQ)
        self._socket.setsockopt(zmq.RCVTIMEO, 8000)
        self._socket.connect(self._address)
        log.info("SilControllers connected to FPrime at %s", self._address)

    def _send_recv(self, data: dict) -> dict:
        self._socket.send_json(data)
        return self._socket.recv_json()

    def drogue_trigger(self, pressure, height, state) -> bool:
        """Ask Orchestrator double buffer whether to fire the drogue chute."""
        resp = self._send_recv({"type": "DROGUE_POLL"})
        return bool(resp.get("drogue", False))

    def main_trigger(self, pressure, height, state) -> bool:
        """Ask Orchestrator double buffer whether to fire the main chute."""
        resp = self._send_recv({"type": "MAIN_POLL"})
        return bool(resp.get("main", False))

    def airbrake_controller(self, time, sampling_rate, state_vector, state_history, observed_variables, air_brakes, sensors, environment):
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
        resp = self._send_recv({"type": "SENSOR", **sensor.to_dict()})

        dep_level = float(resp.get("airbrake_dep_level", 0.0))

        if dep_level > 0 or air_brakes.deployment_level > 0:
            log.info(f"DEP {time:.4f} {dep_level:.6f}")

        air_brakes.deployment_level = dep_level
        return time

    def close(self):
        if self._socket:
            self._socket.close()
            self._socket = None
            log.info("SilControllers socket closed")