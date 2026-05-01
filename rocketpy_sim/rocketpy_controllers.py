from models.sensor_data import SensorData
import zmq
import logging

log = logging.getLogger("ritl.controllers")

ORCHESTRATOR_ADDRESS = "tcp://127.0.0.1:5560"

TARGET_APOGEE = 3000
Kp = 0.0001
Ki = 0.00001
BOOST_ACCEL_THRESHOLD = 15.0

pid = {
    "integral":   0.0,
    "prev_dep":   0.0,
    "vz":         0.0,
    "prev_alt":   None,
    "burned_out": False,
    "descent_count": 0,
}

class RocketPyControllers:
    def __init__(self, ctx):
        self.socket = ctx.socket(zmq.REQ)
        self.socket.setsockopt(zmq.RCVTIMEO, 2000)

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
        air_brakes.deployment_level = float(resp.get("airbrake_dep_level"))
        return time

# Non sim functions
    def drogue_trigger_non_sim(self, pressure, height, state):
        return True if state[5] < 5 and state[2] > 300 else False

    def main_trigger_non_sim(self, pressure, height, state):
        return False

    # def airbrake_controller_non_sim(self, time, sampling_rate, state_vector, state_history, observed_variables, air_brakes, sensors, environment):
    #     new_deployment_level = 0

    #     if time <= 11.4:
    #         new_deployment_level = 1
    #     else:
    #         new_deployment_level = (
    #             -0.002906 * np.power(time, 3)
    #             + 0.1497 * np.power(time, 2)
    #             + -2.563 * time
    #             + 14.96
    #         )

    #     if time > 19.6:
    #         new_deployment_level = 0

    #     if time < 3.8:
    #         new_deployment_level = 0

    #     air_brakes.deployment_level = new_deployment_level

    #     return time, air_brakes.deployment_level



    def airbrake_controller_non_sim(self,
        time, sampling_rate, state_vec, state_history,
        observed_variables, air_brakes, sensors, environment
    ):
        # return False
        dt = 1.0 / sampling_rate

        accel = sensors[0].measurement
        baro = sensors[1].measurement
        gyro = sensors[2].measurement


        pressure = baro
        (ax, ay, az) = accel
        (wx, wy, wz) = gyro

        P0 = environment.pressure(environment.elevation)
        altitude = 44330.0 * (1.0 - (pressure / P0) ** (1.0 / 5.255))

        # during boost az is large
        if not pid["burned_out"]:
            if az > BOOST_ACCEL_THRESHOLD:
                # still burning
                pid["vz"]      = 0.0
                pid["prev_alt"] = altitude
                air_brakes.deployment_level = 0
                return (time, 0.0, altitude)
            else:
                pid["burned_out"] = True

        g = 9.81
        pid["vz"] += az * dt # euler integration here to get velicity in z

        # checks if we are past apogee
        if pid["prev_alt"] is not None:
            if altitude < pid["prev_alt"]:
                pid["descent_count"] += 1
            else:
                pid["descent_count"] = 0

            if pid["descent_count"] >= 10:
                air_brakes.deployment_level = 0
                pid["integral"]  = 0.0
                pid["prev_dep"]  = 0.0
                pid["burned_out"] = False
                return (time, 0.0, altitude)

        pid["prev_alt"] = altitude

        vz = pid["vz"]

        predicted_apogee = altitude + (vz**2) / (2 * g)

        error = predicted_apogee - TARGET_APOGEE
        pid["integral"] += error * dt
        pid["integral"] = max(-1000, min(1000, pid["integral"]))

        raw     = Kp * error + Ki * pid["integral"]
        new_dep = max(0.0, min(1.0, raw))

        air_brakes.deployment_level = new_dep

        return (time, new_dep, altitude, predicted_apogee, vz)
    def close(self):
        self.socket.close()