import zmq
import threading
import logging
from .sensor_tcp_client import FswTcpClient
from .actuation_tcp_server import ActuationTcpServer
from models.flag_store import FlagStore
from models.sensor_data import SensorData

# logging.basicConfig(filename='test.log', encoding='utf-8', level=logging.DEBUG)
log = logging.getLogger("ritl.orchestrator")

ROCKETPY_ADDRESS = "tcp://127.0.0.1:5560"

FSW_HOST         = "host.docker.internal"
ACTUATION_BIND   = "0.0.0.0"
FSW_TCP_PORT     = 50100
ACTUATION_PORT   = 50101

class Orchestrator:
    def __init__(self, ctx, ready_event: threading.Event = None):
        self.ctx = ctx
        self._ready_event = ready_event
        self._flag_store = FlagStore()
        self._fsw = FswTcpClient(FSW_HOST, FSW_TCP_PORT)
        self._actuation = ActuationTcpServer(
            host = ACTUATION_BIND,
            port = ACTUATION_PORT,
            flag_store = self._flag_store,
        )

    def run(self):
        self._fsw.connect()
        self._actuation.start()

        rocketpy_socket = self.ctx.socket(zmq.REP)
        rocketpy_socket.bind(ROCKETPY_ADDRESS)

        if self._ready_event:
            self._ready_event.set()

        while True:
            try:
                msg = rocketpy_socket.recv_json()
                msg_type = msg.get("type")

                if msg_type == "SENSOR":
                    sensor = SensorData.from_dict(msg)
                    log.info(f"Telemetry: t={sensor.t}, baro={sensor.baro}")
                    self._fsw.send_sensor(sensor)
                    rocketpy_socket.send_json({"status": "ok"}) # just an ack to continue lockstep

                elif msg_type in ("DROGUE_POLL", "MAIN_POLL"):
                    flags = self._flag_store.snapshot()
                    rocketpy_socket.send_json({**flags})

                else:
                    log.warning(f"Unknown message: {msg_type}")

            except Exception as e:
                log.error(f"Orchestrator error: {e}")

    def close(self):
        self._actuation.close()
        self._fsw.close()
        self.ctx.destroy()