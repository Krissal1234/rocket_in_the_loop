import threading
import logging
from .actuation_data import ActuationCommand, CommandId

log = logging.getLogger("ritl.flag_store")

class FlagStore:
    def __init__(self):
        self._flags = {
            "drogue":False,
            "main": False,
            "airbrake_dep_level": 0.0,
        }
        self._lock = threading.Lock()
        self._airbrake_event = threading.Event()
        self._fsw_active = False # If FSW not sending airbrake commands then we skip - no need to wait as airbrakes are now off

    def actuate(self, cmd: ActuationCommand) -> None:
        with self._lock:
            if cmd.cmd_id == CommandId.DROGUE_FIRE:
                self._flags["drogue"] = True
            elif cmd.cmd_id == CommandId.MAIN_FIRE:
                self._flags["main"] = True
            elif cmd.cmd_id == CommandId.AIRBRAKE_SET:
                self._flags["airbrake_dep_level"] = cmd.deployment_level
                self._fsw_active = True
            else:
                log.warning(f"FlagStore: unknown command {cmd.cmd_id:#04x}")
        if cmd.cmd_id == CommandId.AIRBRAKE_SET:
            self._airbrake_event.set()

    def wait_for_airbrake(self, timeout: float = 2.0) -> float:
        with self._lock:
            if not self._fsw_active:
                return self._flags["airbrake_dep_level"]

        self._airbrake_event.clear()
        got = self._airbrake_event.wait(timeout=timeout)

        with self._lock:
            if not got:
                self._fsw_active = False
                log.debug("FlagStore: F-Prime went silent, switching to non-blocking")
            return self._flags["airbrake_dep_level"]

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._flags)

    def reset(self) -> None:
        with self._lock:
            self._flags = {
                "drogue": False,
                "main": False,
                "airbrake_dep_level": 0.0,
            }
            self._fsw_active = False
        self._airbrake_event.clear()
