#!/usr/bin/env python3
"""
Repeatability test runner.

Usage:
    # non-sil baseline
    python run_repeatability.py --mode nonsil --rocket calisto

    # sensor driven, 10 runs
    python run_repeatability.py --mode sil --arch sensordriven --rocket calisto --runs 10

    # rate group sweep
    python run_repeatability.py --mode sil --arch rategroup --rate-hz 1  --rocket calisto --runs 10
    python run_repeatability.py --mode sil --arch rategroup --rate-hz 5  --rocket calisto --runs 10
    python run_repeatability.py --mode sil --arch rategroup --rate-hz 10 --rocket calisto --runs 10
    python run_repeatability.py --mode sil --arch rategroup --rate-hz 25 --rocket calisto --runs 10

    # lockstep
    python run_repeatability.py --mode sil --arch lockstep --rocket calisto --runs 10
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
RUN_TIMEOUT = 600
FPRIME_GDS_DIR = Path.home() / "Documents/projects/thesis/ritl-fsw/RitlFsw/SilDeployment"
FPRIME_VENV    = Path.home() / "Documents/projects/thesis/ritl-fsw/fprime-venv"

DOCKER_COMPOSE_RUN = [
    "docker", "compose", "run", "--rm", "--service-ports", "ritl",
    "python", "main.py",
]


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def kill_fprime_gds():
    log("Killing any running fprime-gds processes...")
    subprocess.run(["docker", "compose", "down"], capture_output=True)
    subprocess.run(["pkill", "-f", "fprime-gds"], capture_output=True)
    subprocess.run(["pkill", "-f", "RitlFsw_SilDeployment"], capture_output=True)
    for port in ["50000", "5000", "50100", "50101"]:
        subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True)
    time.sleep(5)


def wait_for_fprime_ready(timeout: int = 60) -> bool:
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
        log("ERROR: FSW never became ready.")
        sys.exit(1)
    return proc


def build_sim_cmd(args, run_id: str) -> list[str]:
    cmd = DOCKER_COMPOSE_RUN + [
        "--mode",   args.mode,
        "--rocket", args.rocket,
        "--run-id", run_id,
    ]
    if args.mode == "sil":
        cmd += ["--arch", args.arch]
        if args.arch == "rategroup":
            cmd += ["--rate-hz", str(args.rate_hz)]
    return cmd


def run_simulation(args, run_id: str) -> bool:
    cmd = build_sim_cmd(args, run_id)
    log(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, timeout=RUN_TIMEOUT)
        if result.returncode != 0:
            log(f"WARNING: process exited with code {result.returncode}")
            return False
        return True
    except subprocess.TimeoutExpired:
        log(f"ERROR: run timed out after {RUN_TIMEOUT}s")
        return False


def run_batch(args, n_runs: int):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    failed = []

    for i in range(1, n_runs + 1):
        run_id = f"{i:03d}"
        print(f"\n{'='*60}")
        log(f"Run {i}/{n_runs}  (id={run_id})")
        print(f"{'='*60}")

        if args.mode == "sil":
            kill_fprime_gds()
            gds_proc = start_fprime_gds(run_id)

        success = run_simulation(args, run_id)

        if args.mode == "sil":
            log("Shutting down fprime-gds...")
            gds_proc.terminate()
            try:
                gds_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                gds_proc.kill()

        if not success:
            failed.append(run_id)

    print(f"\n{'='*60}")
    log(f"Batch complete. {n_runs - len(failed)}/{n_runs} succeeded.")
    if failed:
        log(f"Failed run IDs: {', '.join(failed)}")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Repeatability test runner")
    parser.add_argument("--mode",     choices=["sil", "nonsil"], required=True)
    parser.add_argument("--arch",     choices=["rategroup", "sensordriven", "lockstep"],
                        default=None, help="Coupling architecture (sil only)")
    parser.add_argument("--rate-hz",  type=int, default=None,
                        help="Rate group Hz (rategroup arch only)")
    parser.add_argument("--rocket",   choices=["calisto", "cameos"], default="calisto")
    parser.add_argument("--runs",     type=int, default=10)
    args = parser.parse_args()

    # validation
    if args.mode == "sil" and args.arch is None:
        parser.error("--arch is required when --mode sil")
    if args.mode == "sil" and args.arch == "rategroup" and args.rate_hz is None:
        parser.error("--rate-hz is required when --arch rategroup")

    n_runs = 1 if args.mode == "nonsil" else args.runs

    label = args.mode if args.mode == "nonsil" else \
            f"{args.arch} {args.rate_hz}Hz" if args.arch == "rategroup" else args.arch

    print(f"\nTest: {label}  rocket={args.rocket}  runs={n_runs}")
    print(f"Logs: {LOGS_DIR.resolve()}\n")

    run_batch(args, n_runs)

    if args.mode == "sil":
        kill_fprime_gds()

    log("All done.")


if __name__ == "__main__":
    main()