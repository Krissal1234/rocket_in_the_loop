import threading
import logging
from .actuation_data import ActuationCommand, CommandId

log = logging.getLogger("ritl.flag_store")

class FlagStore:
    def __init__(self):
        self._flags = {
            "drogue": False,
            "main":   False,
            "airbrake_dep_level": 0.0,
        }
        self._lock = threading.Lock()
        self._airbrake_event = threading.Event()

    def actuate(self, cmd: ActuationCommand) -> None:
        with self._lock:
            if cmd.cmd_id == CommandId.DROGUE_FIRE:
                self._flags["drogue"] = True
                log.info("FlagStore: drogue fired")
            elif cmd.cmd_id == CommandId.MAIN_FIRE:
                self._flags["main"] = True
                log.info("FlagStore: main fired")
            elif cmd.cmd_id == CommandId.AIRBRAKE_SET:
                self._flags["airbrake_dep_level"] = cmd.deployment_level
            else:
                log.warning(f"FlagStore: unknown command {cmd.cmd_id:#04x}")
        if cmd.cmd_id == CommandId.AIRBRAKE_SET:
            self._airbrake_event.set()  # outside lock

    def wait_for_airbrake(self, timeout: float = 0.5) -> float:
        fired = self._airbrake_event.wait(timeout=timeout)
        self._airbrake_event.clear()
        if not fired:
            log.warning("FlagStore: airbrake wait timed out — returning last known value")
        with self._lock:
            return self._flags["airbrake_dep_level"]


    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._flags)

    def reset(self) -> None:
        with self._lock:
            self._flags = {
                "drogue":             False,
                "main":               False,
                "airbrake_dep_level": 0.0,
            }
        self._airbrake_event.clear()