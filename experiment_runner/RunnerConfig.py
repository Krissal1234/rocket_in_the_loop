from EventManager.Models.RunnerEvents import RunnerEvents
from EventManager.EventSubscriptionController import EventSubscriptionController
from ConfigValidator.Config.Models.RunTableModel import RunTableModel
from ConfigValidator.Config.Models.FactorModel import FactorModel
from ConfigValidator.Config.Models.RunnerContext import RunnerContext
from ConfigValidator.Config.Models.OperationType import OperationType
from ExtendedTyping.Typing import SupportsStr
from ProgressManager.Output.OutputProcedure import OutputProcedure as output

from typing import Dict, Optional
from pathlib import Path
from os.path import dirname, realpath
import subprocess
import socket
import shutil
import time
import re
import yaml



ROCKET = "cameos"
N_RUNS = 10
RUN_TIMEOUT = 600    # seconds


HIL_IP           = "10.42.0.142"
FSW_SENSOR_PORT  = 50100
FSW_STARTUP_WAIT = 60

FPRIME_BIN     = Path.home() / "Documents/projects/thesis/ritl-fsw/RitlFsw/SilDeployment/build-artifacts/Linux/RitlFsw_SilDeployment/bin/RitlFsw_SilDeployment"
FPRIME_GDS_DIR = Path.home() / "Documents/projects/thesis/ritl-fsw/RitlFsw/SilDeployment"
FPRIME_VENV    = Path.home() / "Documents/projects/thesis/ritl-fsw/fprime-venv"

# HIL — Raspberry Pi running the FSW binary
HIL_SSH_USER = "pi"
HIL_SSH_HOST = HIL_IP
HIL_FSW_BIN  = "/home/pi/RitlFsw_SilDeployment"   # path on the Pi

RUNNER_DIR  = Path(dirname(realpath(__file__)))
RITL_DIR    = RUNNER_DIR.parent / "Ritl"        # contains docker-compose.yml
RITL_CONFIG = RITL_DIR / "config.yaml"
RITL_LOGS   = RITL_DIR / "logs"                 # where main.py writes logs

SIL_HOST = "127.0.0.1"

DOCKER_COMPOSE_RUN = [
    "docker", "compose", "run", "--rm", "--service-ports", "ritl",
    "python", "main.py",
]

RE_APOGEE    = re.compile(r"APOGEE\s+([\d.]+)\s+([\d.]+)")
RE_DROGUE    = re.compile(r"DROGUE\s+([\d.]+)")
RE_MAIN      = re.compile(r"MAIN\s+([\d.]+)")
RE_WALL_TIME = re.compile(r"WALL_TIME\s+([\d.]+)")

# ─────────────────────────────────────────────────────────────────────────────


class RunnerConfig:
    ROOT_DIR = RUNNER_DIR

    name:                    str           = "ritl_experiment_2"
    results_output_path:     Path          = ROOT_DIR / "experiments"
    operation_type:          OperationType = OperationType.AUTO
    time_between_runs_in_ms: int           = 3000

    def __init__(self):
        EventSubscriptionController.subscribe_to_multiple_events([
            (RunnerEvents.BEFORE_EXPERIMENT, self.before_experiment),
            (RunnerEvents.BEFORE_RUN,        self.before_run),
            (RunnerEvents.START_RUN,         self.start_run),
            (RunnerEvents.START_MEASUREMENT, self.start_measurement),
            (RunnerEvents.INTERACT,          self.interact),
            (RunnerEvents.STOP_MEASUREMENT,  self.stop_measurement),
            (RunnerEvents.STOP_RUN,          self.stop_run),
            (RunnerEvents.POPULATE_RUN_DATA, self.populate_run_data),
            (RunnerEvents.AFTER_EXPERIMENT,  self.after_experiment),
        ])
        self.run_table_model = None
        self._fprime_proc: Optional[subprocess.Popen] = None
        self._current_mode: str = ""
        output.console_log("RITL RunnerConfig loaded")

    # ── Run table ─────────────────────────────────────────────────────────────
    def create_run_table_model(self) -> RunTableModel:
        mode_factor = FactorModel("mode", [
            "nonsil",
            "sil_lockstep",
            "sil_snapshot",
            "hil_lockstep",
            "hil_snapshot",
        ])
        self.run_table_model = RunTableModel(
            factors=[mode_factor],
            repetitions=N_RUNS,
            data_columns=["apogee_m", "apogee_time_s", "drogue_s", "main_s", "wall_time_s", "success"],
        )
        return self.run_table_model

    def _log_path(self, mode: str) -> Path:
        if mode == "nonsil":
            return RITL_LOGS / f"nonsil_default_{ROCKET}.log"
        arch = mode.split("_", 1)[1]   # lockstep | snapshot | sensordriven | rategroup
        return RITL_LOGS / f"sil_{arch}_{ROCKET}.log"

    def _patch_ritl_config(self, mode: str) -> None:
        with open(RITL_CONFIG) as f:
            cfg = yaml.safe_load(f)

        if mode == "nonsil":
            cfg["mode"] = "nonsil"
            cfg["arch"] = None
        elif mode.startswith("hil"):
            arch = mode.split("_", 1)[1]   # lockstep | snapshot |
            cfg["mode"] = "sil"
            cfg["arch"] = arch
            cfg["network"]["fsw_host"] = HIL_IP
        else:  # sil_lockstep | sil_snapshot |
            arch = mode.split("_", 1)[1]
            cfg["mode"] = "sil"
            cfg["arch"] = arch
            cfg["network"]["fsw_host"] = SIL_HOST

        cfg["rocket"]  = ROCKET
        cfg["log_dir"] = "logs"   # relative — main.py runs from /app inside container

        with open(RITL_CONFIG, "w") as f:
            yaml.dump(cfg, f, default_flow_style=False)

        output.console_log(f"Config patched: mode={cfg['mode']}, arch={cfg.get('arch')}, fsw_host={cfg['network'].get('fsw_host', 'n/a')}")

    def _kill_fprime(self) -> None:
        output.console_log("Killing any existing F Prime / GDS processes...")
        subprocess.run(["docker", "compose", "down"], cwd=RITL_DIR, capture_output=True)
        subprocess.run(["pkill", "-f", "fprime-gds"],    capture_output=True)
        subprocess.run(["pkill", "-f", FPRIME_BIN.name], capture_output=True)
        for port in [50000, 5000, FSW_SENSOR_PORT, 50101]:
            subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True)
        time.sleep(5)

    def _wait_for_fprime(self, timeout: int = FSW_STARTUP_WAIT, host: str = "127.0.0.1") -> bool:
        output.console_log(f"Waiting for FSW on {host}:{FSW_SENSOR_PORT}...")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with socket.create_connection((host, FSW_SENSOR_PORT), timeout=1):
                    output.console_log("FSW is ready.")
                    return True
            except OSError:
                time.sleep(0.5)
        output.console_log("WARNING: FSW did not become ready in time.")
        return False

    def _start_fprime(self, run_dir: Path) -> None:
        output.console_log("Starting fprime-gds...")
        self._fprime_proc = subprocess.Popen(
            f"source {FPRIME_VENV}/bin/activate && fprime-gds",
            cwd=FPRIME_GDS_DIR,
            shell=True,
            executable="/bin/bash",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not self._wait_for_fprime():
            output.console_log("ERROR: FSW never became ready — aborting run.")
            self._fprime_proc.kill()
            self._fprime_proc = None

    def _kill_hil_fsw(self) -> None:
        output.console_log(f"Killing FSW on Pi ({HIL_SSH_HOST})...")
        subprocess.run(
            ["ssh", f"{HIL_SSH_USER}@{HIL_SSH_HOST}", f"pkill -f {HIL_FSW_BIN.split('/')[-1]} || true"],
            capture_output=True,
        )
        subprocess.run(["fuser", "-k", f"{FSW_SENSOR_PORT}/tcp"], capture_output=True)
        time.sleep(3)

    def _start_hil_fsw(self, run_dir: Path) -> None:
        output.console_log(f"Starting FSW binary on Pi: {HIL_SSH_HOST}:{HIL_FSW_BIN}")
        log_file = open(run_dir / "hil_fsw.log", "w")
        self._fprime_proc = subprocess.Popen(
            ["ssh", f"{HIL_SSH_USER}@{HIL_SSH_HOST}", HIL_FSW_BIN],
            stdout=log_file,
            stderr=log_file,
        )
        if not self._wait_for_fprime(host=HIL_IP):
            output.console_log("ERROR: HIL FSW never became ready — aborting run.")
            self._fprime_proc.kill()
            self._fprime_proc = None

    def _parse_log(self, log_path: Path) -> Optional[Dict]:
        if not log_path.exists():
            output.console_log(f"WARNING: log not found at {log_path}")
            return None

        text = log_path.read_text()
        apogee = apogee_time = drogue = main = wall_time = None

        for line in text.splitlines():
            if apogee is None:
                m = RE_APOGEE.search(line)
                if m:
                    apogee      = float(m.group(1))
                    apogee_time = float(m.group(2))
            if drogue is None:
                m = RE_DROGUE.search(line)
                if m:
                    drogue = float(m.group(1))
            if main is None:
                m = RE_MAIN.search(line)
                if m:
                    main = float(m.group(1))
            if wall_time is None:
                m = RE_WALL_TIME.search(line)
                if m:
                    wall_time = float(m.group(1))

        if None in (apogee, apogee_time, drogue, main):
            output.console_log("WARNING: incomplete log — some metrics missing.")
            return None

        return {
            "apogee_m":      apogee,
            "apogee_time_s": apogee_time,
            "drogue_s":      drogue,
            "main_s":        main,
            "wall_time_s":   wall_time,
        }

    def before_experiment(self) -> None:
        output.console_log(f"Starting RITL experiment | runs={N_RUNS}")
        output.console_log(f"RITL dir:    {RITL_DIR}")
        output.console_log(f"RITL config: {RITL_CONFIG}")
        output.console_log(f"Logs dir:    {RITL_LOGS}")
        RITL_LOGS.mkdir(parents=True, exist_ok=True)

    def before_run(self) -> None:
        output.console_log("Preparing for next run...")
        subprocess.run(["docker", "compose", "down"], cwd=RITL_DIR, capture_output=True)
        # Delete stale logs so the next run starts fresh and we don't parse the wrong run
        for f in RITL_LOGS.glob("*.log"):
            f.unlink()
        time.sleep(2)


    def start_run(self, context: RunnerContext) -> None:
        mode = context.execute_run["mode"]
        run_id = context.execute_run["__run_id"]
        output.console_log(f"Starting run: mode={mode}")

        self._patch_ritl_config(mode)
        self._current_mode = mode   # used by stop_run to clean up the right FSW
        if mode.startswith("hil"):
            self._kill_hil_fsw()
            self._start_hil_fsw(context.run_dir)
        elif mode.startswith("sil"):
            self._kill_fprime()
            self._start_fprime(context.run_dir)
        # nonsil: no FSW needed

    def start_measurement(self, context: RunnerContext) -> None:
        pass

    def interact(self, context: RunnerContext) -> None:
        """Launch the simulation via docker compose run and block until done."""
        output.console_log(f"Launching: {' '.join(DOCKER_COMPOSE_RUN)}")
        try:
            result = subprocess.run(
                DOCKER_COMPOSE_RUN,
                cwd=RITL_DIR,
                timeout=RUN_TIMEOUT,
            )
            if result.returncode != 0:
                output.console_log(f"WARNING: simulation exited with code {result.returncode}")
        except subprocess.TimeoutExpired:
            output.console_log(f"ERROR: simulation timed out after {RUN_TIMEOUT}s")

    def stop_measurement(self, context: RunnerContext) -> None:
        pass

    def stop_run(self, context: RunnerContext) -> None:
        output.console_log("Stopping run...")
        subprocess.run(["docker", "compose", "down"], cwd=RITL_DIR, capture_output=True)

        if self._fprime_proc is not None:
            output.console_log("Terminating FSW process...")
            self._fprime_proc.terminate()
            try:
                self._fprime_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._fprime_proc.kill()
            self._fprime_proc = None
            # Clean up whichever FSW was running
            mode = getattr(self, "_current_mode", "")
            if mode.startswith("hil"):
                self._kill_hil_fsw()
            else:
                self._kill_fprime()

    def populate_run_data(self, context: RunnerContext) -> Optional[Dict[str, SupportsStr]]:
        mode     = context.execute_run["mode"]
        run_id   = context.execute_run["__run_id"]
        log_path = self._log_path(mode)

        output.console_log(f"Parsing log: {log_path}")
        parsed = self._parse_log(log_path)

        if parsed is None:
            return {"apogee_m": None, "apogee_time_s": None, "drogue_s": None,
                    "main_s": None, "wall_time_s": None, "success": False}

        # Copy log + any other outputs (CSV, plots) into the experiment run dir
        src_stem  = log_path.stem   # e.g. sil_lockstep_cameos
        dest_stem = f"{mode}_{run_id}"
        for f in RITL_LOGS.iterdir():
            if f.stem == src_stem:
                shutil.copy(f, context.run_dir / f"{dest_stem}{f.suffix}")

        return {
            "apogee_m":      parsed["apogee_m"],
            "apogee_time_s": parsed["apogee_time_s"],
            "drogue_s":      parsed["drogue_s"],
            "main_s":        parsed["main_s"],
            "wall_time_s":   parsed["wall_time_s"],
            "success":       True,
        }

    def after_experiment(self) -> None:
        output.console_log("Experiment complete.")
        output.console_log(f"Results saved to: {self.results_output_path / self.name}")

    experiment_path: Path = None