# models/flag_store.py
import threading
import logging
from .actuation_data import ActuationCommand, CommandId

log = logging.getLogger("ritl.flag_store")

class FlagStore:
    def __init__(self):
        self._flags = {
            "drogue": False,
            "main":   False,
            "airbrake_dep_level": 0,
        }
        self._lock = threading.Lock()

    def actuate(self, cmd: ActuationCommand) -> None:
      # used by actuation command to set flag values
        with self._lock:
            if cmd.cmd_id == CommandId.DROGUE_FIRE:
                self._flags["drogue"] = True
            elif cmd.cmd_id == CommandId.MAIN_FIRE:
                self._flags["main"] = True
            elif cmd.cmd_id == CommandId.AIRBRAKE_SET:
                self._flags["airbrake_dep_level"] = cmd.deployment_level
            else:
                log.warning(f"FlagStore: unknown command {cmd.cmd_id:#04x}")

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._flags)

    def reset(self) -> None:
        with self._lock:
            self._flags = {
                "drogue":            False,
                "main":              False,
                "airbrake_dep_level": 0.0,
            }