import argparse
import threading
import logging
import time
import os
import zmq
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import rockets.cameos as cameos
import rockets.calisto as calisto
from orchestrator.orchestrator import Orchestrator
from controllers.controllers_non_sil import NonSilControllers
from controllers.controllers_sil import SilControllers


def parse_args():
    parser = argparse.ArgumentParser(description="RocketPy SIL/Non-SIL runner")
    parser.add_argument(
        "--mode",
        choices=["sil", "nonsil"],
        required=True,
        help="Simulation mode",
    )
    parser.add_argument(
        "--arch",
        choices=["rategroup", "sensordriven", "lockstep"],
        default=None,
        help="Coupling architecture (only used in sil mode)",
    )
    parser.add_argument(
        "--rate-hz",
        type=int,
        default=None,
        help="Rate group frequency in Hz (only used with --arch rategroup)",
    )
    parser.add_argument(
        "--rocket",
        choices=["calisto", "cameos"],
        default="calisto",
        help="Which rocket to simulate",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Run identifier appended to log filename, e.g. '001'",
    )
    return parser.parse_args()


def build_prefix(args) -> str:
    """Construct a consistent filename prefix from run parameters."""
    if args.mode == "nonsil":
        return f"nonsil_{args.rocket}"

    # sil mode — arch is required
    if args.arch == "rategroup":
        if args.rate_hz is None:
            raise ValueError("--rate-hz is required when --arch rategroup")
        return f"rategroup_{args.rate_hz}hz_{args.rocket}"
    else:
        return f"{args.arch}_{args.rocket}"


def main():
    args = parse_args()
    enable_sil = args.mode == "sil"

    prefix = build_prefix(args)
    suffix = f"_{args.run_id}" if args.run_id else ""
    base   = f"logs/{prefix}{suffix}"

    os.makedirs("logs", exist_ok=True)

    logging.basicConfig(
        filename=f"{base}.log",
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
    )
    log = logging.getLogger("ritl")
    log.info(f"Starting in {'SIL' if enable_sil else 'Non-SIL'} mode")
    log.info(f"arch={args.arch}  rate_hz={args.rate_hz}  rocket={args.rocket}")

    ctx = zmq.Context.instance()

    if enable_sil:
        ready = threading.Event()
        orch = Orchestrator(ctx, ready_event=ready)
        ctrl = SilControllers(ctx)
        orch_thread = threading.Thread(target=orch.run, name="orchestrator", daemon=True)
        orch_thread.start()
        ready.wait()
        log.info("orchestrator ready")
        ctrl.connect()
    else:
        ctrl = NonSilControllers()

    log.info("building flight...")
    time.sleep(1)

    sim_start_time = time.time()

    if args.rocket == "calisto":
        flight = calisto.build(ctrl, enable_sil=enable_sil)
    else:
        flight = cameos.build(ctrl, enable_sil=enable_sil)

    # ── parachute events ──────────────────────────────────────────────────────
    drogue_time = None
    main_time   = None
    for t, chute in flight.parachute_events:
        if "drogue" in chute.name.lower() and drogue_time is None:
            drogue_time = t
        if "main" in chute.name.lower() and main_time is None:
            main_time = t

    # ── scalar metrics ────────────────────────────────────────────────────────
    apogee_agl = flight.apogee - flight.env.elevation

    log.info(f"APOGEE {apogee_agl:.4f} {flight.apogee_time:.4f}")
    log.info(f"DROGUE {drogue_time:.4f}")
    log.info(f"MAIN   {main_time:.4f}")
    log.info(f"WALL_TIME {time.time() - sim_start_time:.4f}")
    log.info("simulation complete")
    log.info("shutting down")

    # ── trajectory CSV ────────────────────────────────────────────────────────
    alt_data = np.array(flight.z.source)
    vz_data  = np.array(flight.vz.source)
    alt_agl  = alt_data[:, 1] - flight.env.elevation

    np.savetxt(
        f"{base}_trajectory.csv",
        np.column_stack([alt_data[:, 0], alt_agl, vz_data[:, 1]]),
        delimiter=",",
        header="t,altitude_agl_m,vz_ms",
        comments="",
    )

    # ── RocketPy plots ────────────────────────────────────────────────────────
    flight.plots.linear_kinematics_data()
    plt.savefig(f"{base}_kinematics.png", dpi=150, bbox_inches="tight")
    plt.close("all")

    flight.plots.trajectory_3d()
    plt.savefig(f"{base}_trajectory3d.png", dpi=150, bbox_inches="tight")
    plt.close("all")


if __name__ == "__main__":
    main()