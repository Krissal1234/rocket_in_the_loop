import threading
import logging
from ritl.models.actuation_data import ActuationCommand, ActuationData, CommandId

log = logging.getLogger("ritl.flag_store")

class FlagStore:
    def __init__(self):
        self._state = ActuationData()
        self._lock = threading.RLock()
        self._silence_logged = False

        self._airbrake_event = threading.Event()
        self._fsw_active = False # If FSW not sending airbrake commands then we skip - no need to wait as airbrakes are now off

    def actuate(self, cmd: ActuationCommand) -> None:

        with self._lock:
            if cmd.cmd_id == CommandId.DROGUE_FIRE:
                self._state.drogue = True
            elif cmd.cmd_id == CommandId.MAIN_FIRE:
                self._state.main = True
            elif cmd.cmd_id == CommandId.AIRBRAKE_SET:
                self._state.airbrake_dep_level = cmd.deployment_level

                self._fsw_active = True
                self._airbrake_event.set()
            else:
                log.warning(f"FlagStore: unknown command {cmd.cmd_id:#04x}")

        # if should_set_event:
        #     self._airbrake_event.set()

    def wait_for_actuation(self, timeout: float = 2.0) -> ActuationData:
        if not self._fsw_active:
            return self.snapshot()

        got = self._airbrake_event.wait(timeout=timeout)

        with self._lock:
            if not got:
                self._fsw_active = False
                if not self._silence_logged:
                    self._silence_logged = True
                    log.debug("FlagStore: F-Prime went silent, switching to non-blocking")

            return ActuationData(
                airbrake_dep_level=self._state.airbrake_dep_level,
                drogue=self._state.drogue,
                main=self._state.main
            )

    def snapshot(self) -> ActuationData:
        with self._lock:
            return ActuationData(
                airbrake_dep_level=self._state.airbrake_dep_level,
                drogue=self._state.drogue,
                main=self._state.main
            )

    def reset(self) -> None:
        with self._lock:
            self._state = ActuationData()
            self._fsw_active = False