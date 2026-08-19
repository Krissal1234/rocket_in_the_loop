import logging
from ritl.bridge.client import BridgeClient
from ritl.models.sensor_data import SensorData

log = logging.getLogger("ritl.controllers.sil")

class SilController:
    """RocketPy controller that forwards sensor data to a SimBridge`
    over ZMQ and applies the returned actuation commands.

    This is the RocketPy-specific adapter for the simulator side"""

    def __init__(self, bridge: BridgeClient):
        self._last_time: float | None = None
        self._bridge = bridge

    # --- RocketPy controller interface ---
    def drogue_trigger(self, pressure, height, state) -> bool:
        return self._bridge.poll_drogue()

    def main_trigger(self, pressure, height, state) -> bool:
        return self._bridge.poll_main()

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

        resp = self._bridge.send_sensor(sensor)
        # dep_level = float(resp.get("airbrake_dep_level", 0.0))
        air_brakes.deployment_level = resp.airbrake_dep_level

        return time
