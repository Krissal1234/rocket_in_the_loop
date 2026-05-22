import zmq
import threading
import logging
from .sensor_tcp_client import FswTcpClient
from .actuation_tcp_server import ActuationTcpServer
from models.flag_store import FlagStore
from models.sensor_data import SensorData
from config import NetworkConfig

log = logging.getLogger("ritl.orchestrator")

parachute_poll_count = 0
sensor_poll_count = 0


class Orchestrator:
    def __init__(self, ctx, network: NetworkConfig, lockstep: bool = True, ready_event: threading.Event = None):
        self.ctx = ctx
        self._lockstep = lockstep
        self._ready_event = ready_event
        self._zmq_address = network.zmq_address
        self._flag_store = FlagStore()
        self._fsw = FswTcpClient(network.fsw_host, network.fsw_sensor_port)
        self._actuation = ActuationTcpServer(
            host="0.0.0.0",
            port=network.fsw_actuation_port,
            flag_store=self._flag_store,
        )

    def run(self):
        global parachute_poll_count, sensor_poll_count
        self._fsw.connect()
        self._actuation.start()

        rocketpy_socket = self.ctx.socket(zmq.REP)
        rocketpy_socket.bind(self._zmq_address)
        log.info("Orchestrator bound to %s  lockstep=%s", self._zmq_address, self._lockstep)

        if self._ready_event:
            self._ready_event.set()

        while True:
            try:
                msg = rocketpy_socket.recv_json()
                msg_type = msg.get("type")

                if msg_type == "SENSOR":
                    sensor = SensorData.from_dict(msg)
                    self._fsw.send_sensor(sensor)

                    # if we are in lockstep we must wait for a response for airbrake control
                    if self._lockstep:
                        dep_level = self._flag_store.wait_for_airbrake(timeout=0.2)
                    else:
                        dep_level = self._flag_store.snapshot()["airbrake_dep_level"]

                    rocketpy_socket.send_json({"airbrake_dep_level": dep_level})
                    sensor_poll_count += 1

                elif msg_type in ("DROGUE_POLL", "MAIN_POLL"):
                    flags = self._flag_store.snapshot()
                    rocketpy_socket.send_json({**flags})
                    parachute_poll_count += 1

                else:
                    log.warning("Unknown message type: %s", msg_type)

            except Exception as e:
                log.error("Orchestrator error: %s", e)

    def close(self):
        log.info("sensor_poll_count=%d  parachute_poll_count=%d", sensor_poll_count, parachute_poll_count)
        self._actuation.close()
        self._fsw.close()
