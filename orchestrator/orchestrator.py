import zmq
import time
import threading
import logging

log = logging.getLogger("ritl.orchestrator")

class Orchestrator:

    def __init__(self,ctx, ready_event: threading.Event = None):
        self._ready_event = ready_event
        self.ctx = ctx

    def run(self):
        try:
            self.rep_socket = self.ctx.socket(zmq.REP)
            self.rep_socket.bind("tcp://127.0.0.1:5559")
            if self._ready_event: self._ready_event.set()

            while True:
                message = self.rep_socket.recv_json()
                print(message)

                self.rep_socket.send_json({"status": "ok"})
        except Exception as e:
            log.error(f"Orchestrator error: {e}")
        finally:
            self.rep_socket.close()