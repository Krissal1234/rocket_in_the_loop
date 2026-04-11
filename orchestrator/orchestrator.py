import zmq
import threading
import logging
from .fsw_client import FswTcpClient

log = logging.getLogger("ritl.orchestrator")

ROCKETPY_ADDRESS    = "tcp://127.0.0.1:5560"
FSW_ACTUATION_BIND  = "tcp://0.0.0.0:5562"

FSW_TCP_HOST = "host.docker.internal"
FSW_TCP_PORT = 50100


class Orchestrator:
    def __init__(self, ctx, ready_event: threading.Event = None):
        self.ctx = ctx # Shared context with rocketpy
        self._ready_event = ready_event
        self._flags = {"drogue": False, "main": False}
        self._flags_lock = threading.Lock()
        self._fsw = FswTcpClient(FSW_TCP_HOST, FSW_TCP_PORT)

    def _actuation_pull_loop(self, fsw_pull):
        while True:
            msg = fsw_pull.recv_json()
            with self._flags_lock:
                if "drogue" in msg:
                    self._flags["drogue"] = bool(msg["drogue"])
                if "main" in msg:
                    self._flags["main"] = bool(msg["main"])
            log.info(f"Flags updated by FSW: {self._flags}")

    def run(self):
        self._fsw.connect()

        rocketpy_socket = self.ctx.socket(zmq.REP)
        rocketpy_socket.bind(ROCKETPY_ADDRESS)

        fsw_pull_socket = self.ctx.socket(zmq.PULL)
        fsw_pull_socket.bind(FSW_ACTUATION_BIND)

        if self._ready_event:
            self._ready_event.set()

        threading.Thread(
            target=self._actuation_pull_loop,
            args=(fsw_pull_socket,),
            daemon=True
        ).start()

        while True:
            try:
                msg = rocketpy_socket.recv_json()
                msg_type = msg.get("type")

                if msg_type == "SENSOR":
                    log.info(f"Telemetry: t={msg.get('t')}")
                    ok = self._fsw.send_sensor(msg)
                    if ok:
                        rocketpy_socket.send_json({"status": "ok"})
                    else:
                        rocketpy_socket.send_json({"status": "error", "reason": "fsw timeout"})

                elif msg_type in ("DROGUE_POLL", "MAIN_POLL"):
                    with self._flags_lock:
                        resp = dict(self._flags)
                    log.info(f"{msg_type} -> {resp}")
                    rocketpy_socket.send_json({**resp, "status": "ok"})

                else:
                    log.warning(f"Unknown message: {msg_type}")
                    rocketpy_socket.send_json({"status": "error", "reason": "unknown type"})

            except Exception as e:
                log.error(f"Orchestrator error: {e}")
                rocketpy_socket.send_json({"status": "error", "reason": str(e)})

    def close(self):
        self._fsw.close()
        self.ctx.destroy()