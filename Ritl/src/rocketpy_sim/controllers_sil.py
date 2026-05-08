import logging
import zmq
from models.sensor_data import SensorData

log = logging.getLogger("ritl.controllers.sil")

ORCHESTRATOR_ADDRESS = "tcp://127.0.0.1:5560"

class SilControllers:
    """
    Software-in-the-Loop controllers.

    Every method is a thin ZMQ proxy: it serialises RocketPy state into
    a message, sends it to the orchestrator, and returns Fsw decision.
    """
    def __init__(self, ctx: zmq.Context, address: str = ORCHESTRATOR_ADDRESS):
        self._ctx     = ctx
        self._address = address
        self._socket  = None
        self._last_time = None

    def connect(self):
        self._socket = self._ctx.socket(zmq.REQ)
        self._socket.setsockopt(zmq.RCVTIMEO, 2000)
        self._socket.connect(self._address)
        log.info("SilControllers connected to FPrime at %s", self._address)

    def _send_recv(self, data: dict) -> dict:
        self._socket.send_json(data)
        return self._socket.recv_json()

    def sensor_controller(self,time, sampling_rate, state,state_history, observed_variables, air_brakes, sensors):

        if time == self._last_time:
            return time

        self._last_time = time

        accel = sensors[0].measurement
        baro = sensors[1].measurement
        gyro = sensors[2].measurement

        sensor = SensorData(
            t = float(time),
            accel_x = float(accel[0]),
            accel_y = float(accel[1]),
            accel_z = float(accel[2]),
            baro = float(baro),
            gyro_x = float(gyro[0]),
            gyro_y = float(gyro[1]),
            gyro_z = float(gyro[2]),
        )

        self._send_recv({"type": "SENSOR", **sensor.to_dict()})
        return time

    def drogue_trigger(self, pressure, height, state) -> bool:
        """Ask Orchestrator double buffer whether to fire the drogue chute."""
        resp = self._send_recv({"type": "DROGUE_POLL"})
        return bool(resp.get("drogue", False))

    def main_trigger(self, pressure, height, state) -> bool:
        """Ask Orchestrator double buffer whether to fire the main chute."""
        resp = self._send_recv({"type": "MAIN_POLL"})
        return bool(resp.get("main", False))

    def airbrake_controller(self, time, sampling_rate, state_vector, state_history, observed_variables, air_brakes, sensors, environment):
        resp = self._send_recv({"type": "AIRBRAKE_POLL"})
        dep_level = resp.get("airbrake_dep_level", 0.0)
        air_brakes.deployment_level = dep_level
        return time

    def close(self):
        if self._socket:
            self._socket.close()
            self._socket = None
            log.info("SilControllers socket closed")