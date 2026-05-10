#!/usr/bin/env python3
"""
Repeatability test runner for SIL vs Non-SIL comparison.

For each run:
  - Sets SIM_MODE env var and passes --run-id to the container
  - For SIL: stops any running fprime-gds, restarts it, then runs docker compose
  - For Non-SIL: just runs docker compose

Logs are written to ../logs/ by the container (mounted volume).

Usage:
    python run_repeatability.py --mode both --runs 20
    python run_repeatability.py --mode sil --runs 10
    python run_repeatability.py --mode nonsil --runs 10
"""

import argparse
import os
import subprocess
import sys
import time
import socket
from datetime import datetime
from pathlib import Path

LOGS_DIR = Path(__file__).parent / "../logs"

FPRIME_STARTUP_WAIT = 15

RUN_TIMEOUT = 600

DOCKER_COMPOSE_RUN = [
    "docker", "compose", "run", "--rm", "--service-ports", "ritl",
    "python", "main.py",
]

FPRIME_GDS_DIR = Path.home() / "Documents/projects/thesis/ritl-fsw/RitlFsw/SilDeployment"
FPRIME_VENV = Path.home() / "Documents/projects/thesis/ritl-fsw/fprime-venv"

def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def kill_fprime_gds():
    log("Killing any running fprime-gds processes...")
    subprocess.run(["docker", "compose", "down"], capture_output=True)
    subprocess.run(["pkill", "-f", "fprime-gds"], capture_output=True)
    subprocess.run(["pkill", "-f", "RitlFsw_SilDeployment"], capture_output=True)
    subprocess.run(["fuser", "-k", "50000/tcp"], capture_output=True)
    subprocess.run(["fuser", "-k", "5000/tcp"], capture_output=True)
    subprocess.run(["fuser", "-k", "50100/tcp"], capture_output=True)
    subprocess.run(["fuser", "-k", "50101/tcp"], capture_output=True)
    time.sleep(5)  # give everything time to fully die


def wait_for_fprime_ready(timeout: int = 60):
    log("Waiting for FSW to be ready on port 50100...")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", 50100), timeout=1):
                log("FSW ready.")
                return True
        except OSError:
            time.sleep(0.5)
    log("WARNING: FSW not ready after timeout.")
    return False


def start_fprime_gds(run_id: str) -> subprocess.Popen:
    log("Starting fprime-gds...")
    gds_log = LOGS_DIR / f"gds_{run_id}.log"
    gds_log.parent.mkdir(parents=True, exist_ok=True)
    gds_out = open(gds_log, "w")
    proc = subprocess.Popen(
        f"source {FPRIME_VENV}/bin/activate && fprime-gds",
        cwd=FPRIME_GDS_DIR,
        shell=True,
        executable="/bin/bash",
        stdout=gds_out,
        stderr=gds_out,
    )
    if not wait_for_fprime_ready():
        gds_out.close()
        log(f"ERROR: FSW never became ready.")
        sys.exit(1)
    return proc


def run_simulation(mode: str, run_id: str) -> bool:
    """Run a single simulation. Returns True on success."""
    cmd = DOCKER_COMPOSE_RUN + ["--mode", mode, "--run-id", run_id]
    env = {**os.environ, "SIM_MODE": mode}

    log(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, env=env, timeout=RUN_TIMEOUT)
        if result.returncode != 0:
            log(f"WARNING: process exited with code {result.returncode}")
            return False
        return True
    except subprocess.TimeoutExpired:
        log(f"ERROR: run timed out after {RUN_TIMEOUT}s")
        return False



def run_batch(mode: str, n_runs: int):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    failed = []

    for i in range(1, n_runs + 1):
        run_id = f"{i:03d}"
        print(f"\n{'='*60}")
        log(f"{mode.upper()} run {i}/{n_runs}  (id={run_id})")
        print(f"{'='*60}")

        if mode == "sil":
            kill_fprime_gds()
            gds_proc = start_fprime_gds(run_id)

        success = run_simulation(mode, run_id)

        if mode == "sil":
            log("Shutting down fprime-gds...")
            gds_proc.terminate()
            try:
                gds_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                gds_proc.kill()

        if success:
            log_path = LOGS_DIR / f"{mode}_{run_id}.log"
            if log_path.exists():
                log(f"Log written: {log_path}")
            else:
                log(f"WARNING: expected log not found at {log_path}")
        else:
            failed.append(run_id)

    print(f"\n{'='*60}")
    log(f"{mode.upper()} batch complete. {n_runs - len(failed)}/{n_runs} succeeded.")
    if failed:
        log(f"Failed run IDs: {', '.join(failed)}")
    print(f"{'='*60}\n")



def main():
    parser = argparse.ArgumentParser(description="Repeatability test runner")
    parser.add_argument(
        "--mode",
        choices=["sil", "nonsil", "both"],
        default="both",
        help="Which condition to run (default: both)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=20,
        help="Number of runs per condition (default: 20)",
    )
    args = parser.parse_args()

    print(f"\nRepeatability test: {args.runs} runs, mode={args.mode}")
    print(f"Logs directory: {LOGS_DIR.resolve()}\n")

    if args.mode in ("nonsil", "both"):
        run_batch("nonsil", args.runs)

    if args.mode in ("sil", "both"):
        run_batch("sil", args.runs)

    log("All done.")


if __name__ == "__main__":
    main()