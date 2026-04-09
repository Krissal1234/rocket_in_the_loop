import zmq
import logging

log = logging.getLogger("ritl.controllers")

ORCHESTRATOR_ADDRESS = "tcp://127.0.0.1:5560"

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

        self._send_recv({
            "type": "SENSOR",
            "t":    time,
            "accel": {"x": accel[0], "y": accel[1], "z": accel[2]},
            "baro":  float(baro),
            "gyro":  {"x": gyro[0],  "y": gyro[1],  "z": gyro[2]},
        })


            # If we want to expose state we can too
            # "pos":   {"x": float(state[0]), "y": float(state[1]), "z": float(state[2])},
            # "vel":   {"x": float(state[3]), "y": float(state[4]), "z": float(state[5])},

        return time

    def drogue_trigger(self, pressure, height, state):
        resp = self._send_recv({"type": "DROGUE_POLL"})
        return bool(resp.get("drogue", False))

    def main_trigger(self, pressure, height, state):
        resp = self._send_recv({"type": "MAIN_POLL"})
        return bool(resp.get("main", False))

    def close(self):
        self.socket.close()