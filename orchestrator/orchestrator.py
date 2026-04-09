# orchestrator.py
import zmq
import threading
import logging

log = logging.getLogger("ritl.orchestrator")

ROCKETPY_ADDRESS    = "tcp://127.0.0.1:5560"
FSW_TELEMETRY_BIND = "tcp://0.0.0.0:5561"    # must go outside docker containerx
FSW_ACTUATION_BIND = "tcp://0.0.0.0:5562"

class Orchestrator:
    def __init__(self, ctx, ready_event: threading.Event = None):
        self.ctx = ctx
        self._ready_event = ready_event
        self._flags = {"drogue": False, "main": False}
        self._flags_lock = threading.Lock()

    def _actuation_pull_loop(self, fsw_pull):
        # these are messages being pushed from FSW for droge or main fire events
        while True:
            msg = fsw_pull.recv_json()
            with self._flags_lock:
                if "drogue" in msg:
                    self._flags["drogue"] = bool(msg["drogue"])
                if "main" in msg:
                    self._flags["main"] = bool(msg["main"])
            log.info(f"Flags updated by FSW: {self._flags}")

    def run(self):
        rocketpy_socket = self.ctx.socket(zmq.REP)
        rocketpy_socket.bind(ROCKETPY_ADDRESS)

        fsw_req_socket = self.ctx.socket(zmq.REQ)
        fsw_req_socket.setsockopt(zmq.RCVTIMEO, 2000)
        fsw_req_socket.connect(FSW_TELEMETRY_BIND)

        fsw_pull_socket = self.ctx.socket(zmq.PULL)
        fsw_pull_socket.bind(FSW_ACTUATION_BIND)

        if self._ready_event:
            self._ready_event.set()

        # we require another thread for the acutation requests from rocketpy
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
                    # we can insert sensor modelling or fault injection here
                    fsw_req_socket.send_json(msg)
                    fsw_ack = fsw_req_socket.recv_json()

                    log.info(f"FSW ack: {fsw_ack}")
                    rocketpy_socket.send_json({"status": "ok"})

                elif msg_type in ("DROGUE_POLL", "MAIN_POLL"):
                    with self._flags_lock:
                        resp = dict(self._flags)
                    log.info(f"{msg_type} → {resp}")
                    rocketpy_socket.send_json({**resp, "status": "ok"})

                else:
                    log.warning(f"Unknown message: {msg_type}")
                    rocketpy_socket.send_json({"status": "error", "reason": "unknown type"})

            except zmq.Again:
                log.error("FSW timed out on telemetry ack")
                rocketpy_socket.send_json({"status": "error", "reason": "fsw timeout"})
            except Exception as e:
                log.error(f"Orchestrator error: {e}")
                rocketpy_socket.send_json({"status": "error", "reason": str(e)})

    def close(self):
        self.ctx.destroy()