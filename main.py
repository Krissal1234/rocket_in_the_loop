import argparse
import threading
import yaml
import logging
import time
import zmq

from orchestrator.orchestrator import Orchestrator
from rocketpy_sim.rocketpy_controllers import RocketPyControllers
from rocketpy_sim.setup import build_flight

ENABLE_SIL = True
logging.basicConfig(
    # filename="test.log",
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s"
)

log = logging.getLogger("ritl")

def main():
    # share context in this test as it is more resource efficient

    ctx = zmq.Context.instance()

    if ENABLE_SIL:
        ready = threading.Event()
        orch = Orchestrator(ctx, ready_event=ready)

    ctrl = RocketPyControllers(ctx)

    if ENABLE_SIL:
        orch_thread = threading.Thread(
            target=orch.run,
            name="orchestrator",
            daemon=True
        )
        orch_thread.start()
        ready.wait()
        log.info("orchestrator ready")
        ctrl.connect()

    log.info("building flight...")


    time.sleep(2)
    flight = build_flight(ENABLE_SIL, ctrl, "data/Camoes_flight")

    flight.all_info()




    # orch.close()

    log.info("simulation complete")

    log.info("shutting down")

if __name__ == "__main__":
    main()