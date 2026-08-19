import os
import threading
import logging
import pandas as pd
import zmq
import time

from ritl.adapters.base import FswAdapter
from ritl.coupling.base import CouplingStrategy
from ritl.models.actuation_data import ActuationData
from ritl.models.sensor_data import SensorData
from ritl.models.fault_injector import FaultInjector, no_faults

log = logging.getLogger("ritl.sim_bridge")


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

        self._sock: zmq.Socket | None = None
        self._ctx: zmq.Context | None = None
        self._stop_event = threading.Event()

        self._telemetry_buffer = []

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

        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.REP)
        self._sock.bind(self._zmq_address)
        log.info("SimBridge bound to %s", self._zmq_address)

        ready.set()
        while not self._stop_event.is_set():
            try:
                msg = self._sock.recv_json()
                reply = self._handle(msg)
                self._sock.send_json(reply)
            except zmq.error.ContextTerminated:
                break
            except Exception as exc:
                log.error("SimBridge error: %s", exc, exc_info=True)
                break

    def _handle(self, msg: dict) -> dict:
        msg_type = msg.get("type")

        if msg_type == "SENSOR":
            sensor = SensorData.from_dict(msg)

            # Fault injection processed here
            processed = self._fault.process(sensor)
            dropped = processed is None

            if not dropped:
                actuation_state = self._coupling.on_sensor(processed, self._fsw)
            else:
                log.info("FAULT dropped at t=%.3f", sensor.t)
                actuation_state = self._fsw.get_snapshot()

            act_dict = actuation_state.to_dict()

            self._telemetry_buffer.append({
                "time": sensor.t,
                "pressure": sensor.baro,
                "accel_x": sensor.accel_x,
                "accel_y": sensor.accel_y,
                "accel_z": sensor.accel_z,
                "gyro_x": sensor.gyro_x,
                "gyro_y": sensor.gyro_y,
                "gyro_z": sensor.gyro_z,
                "dropped": int(dropped),
                "commanded_airbrake": act_dict.get("airbrake_dep_level", 0.0),
            })

            return act_dict

        if msg_type in ("DROGUE_POLL", "MAIN_POLL"):
            return self._fsw.get_snapshot().to_dict()

        log.warning("Unknown message type: %s", msg_type)
        return {}

    def save_telemetry(self, base_path: str) -> None:
        csv_path = f"{base_path}_bridge_telemetry.csv"
        if not self._telemetry_buffer:
            log.warning("Bridge telemetry buffer is empty. Nothing to save.")
            return

        try:
            df = pd.DataFrame(self._telemetry_buffer)
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)
            df.to_csv(csv_path, index=False)
            log.info("Bridge telemetry saved successfully to %s (%d records)", csv_path, len(df))
        except Exception as exc:
            log.error("Failed to save bridge telemetry CSV: %s", exc, exc_info=True)

    def stop(self):
        self._stop_event.set()
        if self._sock:
            self._sock.close(linger=0)
        if self._ctx:
            self._ctx.term()
        if self._fsw:
            self._fsw.stop()
