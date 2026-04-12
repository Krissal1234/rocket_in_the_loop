import argparse
import threading
import yaml
import logging
import time
import zmq

from orchestrator.orchestrator import Orchestrator
from rocketpy_sim.rocketpy_controllers import RocketPyControllers
from rocketpy_sim.setup import build_flight

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s"
)
log = logging.getLogger("ritl")

def main():
    # share context in this test as it is more resource efficient

    ctx = zmq.Context.instance()

    ready = threading.Event()

    orch = Orchestrator(ctx, ready_event=ready)

    ctrl = RocketPyControllers(ctx)

    orch_thread = threading.Thread(
        target=orch.run,
        name="orchestrator",
        daemon=True
    )
    orch_thread.start()

    ready.wait()
    log.info("orchestrator ready")


    log.info("building flight...")
    ctrl.connect()


    flight = build_flight(True, ctrl, "data/test_flight_1")

    flight.all_info()

    log.info("simulation complete")

    log.info("shutting down")

if __name__ == "__main__":
    main()