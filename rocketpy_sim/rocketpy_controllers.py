from models.sensor_data import SensorData
import zmq
import logging

log = logging.getLogger("ritl.controllers")

ORCHESTRATOR_ADDRESS = "tcp://127.0.0.1:5560"

TARGET_APOGEE = 3000
Kp = 0.001
Ki = 0.0001
BOOST_ACCEL_THRESHOLD = 15.0
INTEGRAL_CLAMP = 1000.0


pid = {
    "integral":   0.0,
    "prev_dep":   0.0,
    "vz":         0.0,
    "prev_alt":   None,
    "burned_out": False,
    "descent_count": 0,
    "P0": None,
}

_recovery = {
    "min_baro":     float("inf"),
    "baro_count":   0,
    "drogue_fired": False,
    "main_fired":   False,
}

APOGEE_BARO_DELTA     = 0.5
APOGEE_CONFIRM_COUNT  = 5
MAIN_DEPLOY_DELTA_HPA = 40.0


class RocketPyControllers:
    def __init__(self, ctx):
        self.socket = ctx.socket(zmq.REQ)
        self.socket.setsockopt(zmq.RCVTIMEO, 2000)
        self._last_time = None

    def connect(self):
        self.socket.connect(ORCHESTRATOR_ADDRESS)
        log.info("RocketPy connected")

    def _send_recv(self, data):
        self.socket.send_json(data)
        return self.socket.recv_json()

    def sensor_controller(self, time, sampling_rate, state, state_history,
                          observed_variables, air_brakes, sensors):
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

        self._send_recv({"type": "SENSOR", **sensor.to_dict()})
        return time


    def drogue_trigger(self, pressure, height, state):
        resp = self._send_recv({"type": "DROGUE_POLL"})
        return bool(resp.get("drogue", False))

    def main_trigger(self, pressure, height, state):
        resp = self._send_recv({"type": "MAIN_POLL"})
        return bool(resp.get("main", False))

    def airbrake_controller(self, time, sampling_rate, state_vector, state_history, observed_variables, air_brakes, sensors, environment):
        resp = self._send_recv({"type": "AIRBRAKE_POLL"})
        dep_lvl = resp.get("airbrake_dep_level")
        log.info(f"dep level {dep_lvl}")
        air_brakes.deployment_level = dep_lvl
        return time

# -------------   Non SiL functions --------------
    def _baro_update(self, p_hpa: float) -> None:
        r = _recovery
        if not r["drogue_fired"]:
            if p_hpa < r["min_baro"]:
                r["min_baro"]   = p_hpa
                r["baro_count"] = 0
            elif p_hpa > r["min_baro"] + APOGEE_BARO_DELTA:
                r["baro_count"] += 1


    def drogue_trigger_non_sim(self, pressure, height, state):
        r = _recovery
        self._baro_update(pressure / 100.0)

        if not r["drogue_fired"] and r["baro_count"] >= APOGEE_CONFIRM_COUNT:
            r["drogue_fired"] = True

        return r["drogue_fired"]


    def main_trigger_non_sim(self, pressure, height, state):
        r = _recovery
        if r["drogue_fired"] and not r["main_fired"]:
            if (pressure / 100.0) >= r["min_baro"] + MAIN_DEPLOY_DELTA_HPA:
                r["main_fired"] = True

        return r["main_fired"]


    def airbrake_controller_non_sim(self,
        time, sampling_rate, state_vec, state_history,
        observed_variables, air_brakes, sensors, environment
    ):
        if time == self._last_time: # just a placeholder as controllers are being called twice
            return False

        if self._last_time is not None:
            dt = time - self._last_time
        else:
            dt = 1.0 / sampling_rate

        self._last_time = time

        accel = sensors[0].measurement
        baro  = sensors[1].measurement
        (ax, ay, az) = accel
        pressure = baro

        # set ground pressure on first call
        if pid["P0"] is None:
            pid["P0"] = pressure
            air_brakes.deployment_level = 0
            return (time, 0.0)

        pid["vz"] += az * dt

        # only act after burnout
        if not pid["burned_out"]:
            if az < BOOST_ACCEL_THRESHOLD:
                pid["burned_out"] = True
            else:
                air_brakes.deployment_level = 0
                return (time, 0.0)

        altitude = 44330.0 * (1.0 - (pressure / pid["P0"]) ** (1.0 / 5.255))


        if pid["prev_alt"] is not None:
            if altitude < pid["prev_alt"]:
                pid["descent_count"] += 1
            else:
                pid["descent_count"] = 0

        if pid["descent_count"] >= 10:
            air_brakes.deployment_level = 0
            pid["integral"] = 0.0
            pid["vz"]       = 0.0
            pid["prev_alt"] = altitude
            return (time, 0.0, altitude)

        pid["prev_alt"] = altitude

        vz = pid["vz"]
        predicted_apogee = altitude + (vz ** 2) / (2 * 9.81)

        error = predicted_apogee - TARGET_APOGEE
        pid["integral"] += error * dt
        pid["integral"] = max(-INTEGRAL_CLAMP, min(INTEGRAL_CLAMP, pid["integral"]))

        raw     = Kp * error + Ki * pid["integral"]
        new_dep = max(0.0, min(1.0, raw))

        log.info(f"t={time:.2f} alt={altitude:.1f} pred={predicted_apogee:.1f} err={error:.1f} dep={new_dep:.3f} vz={vz:.2f}")

        air_brakes.deployment_level = new_dep
        return (time, new_dep, altitude, predicted_apogee, vz)

    def close(self):
        self.socket.close()