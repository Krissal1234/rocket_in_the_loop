import argparse
import threading
import logging
import time
import os
import zmq
from orchestrator.orchestrator import Orchestrator
from rocketpy_sim.controllers_non_sil import NonSilControllers
from rocketpy_sim.controllers_sil import SilControllers
from rocketpy_sim.setup import build_flight


def parse_args():
    parser = argparse.ArgumentParser(description="RocketPy SIL/Non-SIL runner")
    parser.add_argument(
        "--mode",
        choices=["sil", "nonsil"],
        required=True,
        help="Simulation mode: 'sil' for Software-in-the-Loop, 'nonsil' for standalone RocketPy",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Optional run identifier appended to log filename, e.g. '001'",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    enable_sil = args.mode == "sil"

    os.makedirs("logs", exist_ok=True)
    suffix = f"_{args.run_id}" if args.run_id else ""
    log_file = f"logs/{args.mode}{suffix}.log"

    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
    )

    log = logging.getLogger("ritl")
    log.info(f"Starting in {'SIL' if enable_sil else 'Non-SIL'} mode")

    ctx = zmq.Context.instance()

    if enable_sil:
        ready = threading.Event()
        orch = Orchestrator(ctx, ready_event=ready)
        ctrl = SilControllers(ctx)
        orch_thread = threading.Thread(
            target=orch.run,
            name="orchestrator",
            daemon=True
        )
        orch_thread.start()
        ready.wait()
        log.info("orchestrator ready")
        ctrl.connect()
    else:
        ctrl = NonSilControllers()

    log.info("building flight...")
    time.sleep(10)
    flight = build_flight(enable_sil, ctrl, "data/Camoes_flight")

    # extracting drogue and main deployent times
    drogue_time = None
    main_time = None
    for t, chute in flight.parachute_events:
        if "drogue" in chute.name.lower() and drogue_time is None:
            drogue_time = t
        if "main" in chute.name.lower() and main_time is None:
            main_time = t

    log.info(f"APOGEE {flight.apogee - flight.env.elevation:.4f} {flight.apogee_time:.4f}")
    log.info(f"DROGUE {drogue_time:.4f}")
    log.info(f"MAIN   {main_time:.4f}")
    log.info("simulation complete")
    log.info("shutting down")


if __name__ == "__main__":
    main()