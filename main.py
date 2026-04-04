import argparse
import threading
import yaml
import logging
import time

# from orchestrator.orchestrator import Orchestrator
from rocketpy_sim.setup import build_flight

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s"
)
log = logging.getLogger("ritl")

def main():

    # orch = Orchestrator()
    # orch_thread = threading.Thread(
    #     target=orch.run,
    #     name="orchestrator",
    #     daemon=True
    # )

    # orch_thread.start()
    # log.info("orchestrator started")
    # time.sleep(0.5)

    log.info("building flight...")
    flight = build_flight("data/test_flight_1")

    log.info("simulation complete")

    time.sleep(1.0)
    log.info("shutting down")

if __name__ == "__main__":
    main()