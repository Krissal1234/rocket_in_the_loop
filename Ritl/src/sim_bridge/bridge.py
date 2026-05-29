import threading
import logging
import zmq

from adapters.base import FswAdapter
from coupling.base import CouplingStrategy
from models.sensor_data import SensorData
from models.fault_injector import FaultInjector, no_faults

log = logging.getLogger("ritl.sim_bridge")

# ZMQ message protocol (simulator-facing interface)
# Any simulator that speaks this JSON protocol over ZMQ REQ/REP can connect.
#
# Inbound messages (simulator --> bridge):
#   SENSOR:      {"type": "SENSOR", "t": float, "baro": float,
#                 "accel": {"x", "y", "z"}, "gyro": {"x", "y", "z"}}
#   DROGUE_POLL: {"type": "DROGUE_POLL"}
#   MAIN_POLL:   {"type": "MAIN_POLL"}
#
# Outbound responses (bridge --> simulator):
#   SENSOR reply:      {"airbrake_dep_level": float}
#   Poll reply:        {"drogue": bool, "main": bool, "airbrake_dep_level": float}


class SimBridge:
    """Bridges any ZMQ-speaking simulator to any FswAdapter.
    Call start_async from the main thread,
    it blocks until the FSW is connected and the ZMQ socket is bound, then
    returns so the simulator can connect."""

    def __init__(
        self,
        fsw: FswAdapter,
        coupling: CouplingStrategy,
        zmq_address: str,
        fault_injector: FaultInjector | None = None,
    ):
        self._fsw = fsw
        self._coupling = coupling
        self._zmq_address = zmq_address
        self._fault = fault_injector or no_faults()
        self._last_logged_s: int = -1

    def start_async(self) -> None:
        """ starts the bridge on a new thread.
            - blocks until the FSW is connected and the ZMQ socket is bound so that the simulator connect immediately after this returns.
        """
        ready = threading.Event()
        threading.Thread(
            target=self._run,
            args=(ready,),
            name="sim-bridge",
            daemon=True,
        ).start()
        ready.wait()

    def _run(self, ready: threading.Event) -> None:
        self._fsw.start()  # connect to FSW blocks until both TCP links are up

        ctx = zmq.Context.instance()
        sock = ctx.socket(zmq.REP)
        sock.bind(self._zmq_address)
        log.info("SimBridge bound to %s", self._zmq_address)

        ready.set()  # unblock the main thread

        while True:
            try:
                msg = sock.recv_json()
                reply = self._handle(msg)
                sock.send_json(reply)
            except Exception as exc:
                log.error("SimBridge error: %s", exc, exc_info=True)
                break

    def _handle(self, msg: dict) -> dict:
        msg_type = msg.get("type")

        if msg_type == "SENSOR":
            sensor = SensorData.from_dict(msg)
            # Fault injection processed here
            processed = self._fault.process(sensor)
            if processed is not None:
                dep = self._coupling.on_sensor(processed, self._fsw)
            else:
                log.debug("FAULT dropped at t=%.3f", sensor.t)
                dep = self._fsw.get_snapshot()["airbrake_dep_level"]

            elapsed_s = int(sensor.t)
            if elapsed_s > self._last_logged_s:
                self._last_logged_s = elapsed_s
                print(
                    f"SIM t={elapsed_s}s baro={sensor.baro:.1f}Pa accel_z={sensor.accel_z:.3f}m/s2 dep={dep:.4f}"
                )

            return {"airbrake_dep_level": dep}

        if msg_type in ("DROGUE_POLL", "MAIN_POLL"):
            return self._fsw.get_snapshot()

        log.warning("Unknown message type: %s", msg_type)
        return {}
