import zmq
import threading
import logging
from .sensor_tcp_client import FswTcpClient
from .actuation_tcp_server import ActuationTcpServer
from models.flag_store import FlagStore
from models.sensor_data import SensorData
from models.config import NetworkConfig
from .fault_injector import FaultInjector, no_faults

log = logging.getLogger("ritl.orchestrator")

class Orchestrator:
    def __init__(self, ctx, network: NetworkConfig, lockstep: bool = True, ready_event: threading.Event = None, fault_injector = None):
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
        self._fault_injector = fault_injector or no_faults()

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
                    sim_t = sensor.t

                    sensor = self._fault_injector.process(sensor)

                    if sensor is not None:
                        self._fsw.send_sensor(sensor)
                    else:
                        log.debug("FAULT packet dropped at t=%.3f", sim_t)

                    # if we are in lockstep we must wait for a response for airbrake control
                    if self._lockstep:
                        dep_level = self._flag_store.wait_for_airbrake(timeout=0.2)
                    else:
                        dep_level = self._flag_store.snapshot()["airbrake_dep_level"]

                    rocketpy_socket.send_json({"airbrake_dep_level": dep_level})

                elif msg_type in ("DROGUE_POLL", "MAIN_POLL"):
                    flags = self._flag_store.snapshot()
                    rocketpy_socket.send_json({**flags})

                else:
                    log.warning("Unknown message type: %s", msg_type)

            except Exception as e:
                log.error("Orchestrator error: %s", e,exc_info=True)
                break

    def close(self):
        log.info("sensor_poll_count=%d  parachute_poll_count=%d", sensor_poll_count, parachute_poll_count)
        self._actuation.close()
        self._fsw.close()
        self._fault_injector.stats()
