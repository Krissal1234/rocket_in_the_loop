import zmq
import logging
import threading

log = logging.getLogger("ritl.controllers")
baseline_orchestrator_address = "tcp://127.0.0.1:5559"


class RocketPyControllers:

    def __init__(self, ctx):
        self._flags = {
            "drogue": False,
            "main":   False,
        }
        self.req_socket = ctx.socket(zmq.REQ)
        self.req_socket.setsockopt(zmq.RCVTIMEO, 1000)

    def connect(self, endpoint=baseline_orchestrator_address):
        log.info(f"Connecting to orchestrator at {endpoint}")
        self.req_socket.connect(endpoint)

    def make_blocking_call(self, data):
        self.req_socket.send_json(data)
        return self.req_socket.recv_json()

    def set_flag(self, channel: str, value: bool):
        with self._lock:
            self._flags[channel] = value
        log.info(f"flag set: {channel}={value}")


    def sensor_controller(self, time, sampling_rate, state, state_history,
                          observed_variables, air_brakes, sensors):
        accel = sensors[0].measurement
        baro  = sensors[1].measurement
        gyro  = sensors[2].measurement

        self.make_blocking_call({
                "type":  "SENSOR",
                "t":     time,
                "accel": list(accel),
                "baro":  float(baro),
                "gyro":  list(gyro),
                "pos":   list(state[0:3]),
                "vel":   list(state[3:6]),
            })


        return time

    def airbrake_controller(self, time, sampling_rate, state, state_history,
                            observed_variables, air_brakes, sensors):
        # try:
        #     msg = self._pull.recv_json(flags=zmq.NOBLOCK)
        #     if msg.get("type") == "AIRBRAKE":
        #         air_brakes.deployment_level = float(msg["level"])
        # except zmq.Again:
        #     pass

        return time, air_brakes.deployment_level

    def drogue_trigger(self, pressure, height, state):
        return self._flags["drogue"]

    def main_trigger(self, pressure, height, state):
        return self._flags["main"]