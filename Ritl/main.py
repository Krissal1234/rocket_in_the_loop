import logging
import time
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import rockets.cameos as cameos
import rockets.calisto as calisto
from models.config import load_config
from models.fault_injector import FaultInjector
from adapters.fprime_adapter import FPrimeAdapter
from coupling import COUPLING_STRATEGIES
from sim_bridge import SimBridge
from controllers.sil import SilController
from controllers.non_sil import NonSilControllers

ROCKETS = {
    "calisto": calisto.build,
    "cameos":  cameos.build,
}

def main():

    cfg = load_config("config.yaml")
    print("CONFIG LOADED", flush=True)

    sample_rate = cfg.rocket_params.sample_rate
    time_step   = cfg.rocket_params.time_step

    base = os.path.join(cfg.log_dir, f"{cfg.mode}_{cfg.arch or 'default'}_{cfg.rocket}")

    os.makedirs(cfg.log_dir, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(name)s] %(message)s")
    file_handler = logging.FileHandler(f"{base}.log", mode="w")
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    log = logging.getLogger("ritl")
    log.info("mode=%s  arch=%s  rocket=%s", cfg.mode, cfg.arch, cfg.rocket)

    fault_injector = FaultInjector(cfg.fault.freeze_baro, cfg.fault.freeze_baro_at, cfg.fault.dropout_rate) if cfg.fault.enabled else None

    if cfg.is_sil:
        arch = cfg.arch or "snapshot"
        if arch not in COUPLING_STRATEGIES:
            raise ValueError(
                f"Unknown arch '{arch}'. Valid: {list(COUPLING_STRATEGIES)}"
            )

        fsw = FPrimeAdapter(cfg.network)
        coupling = COUPLING_STRATEGIES[arch]()
        bridge = SimBridge(fsw, coupling, cfg.network.zmq_address, fault_injector)

        print("WAITING FOR FPRIME", flush=True)

        bridge.start_async()  # connects to FSW + binds ZMQ, then returns
        ctrl = SilController(cfg.network.zmq_address)
        ctrl.connect()
    else:
        ctrl = NonSilControllers()

    log.info("building flight...")
    log.info("sample_rate=%sHz  time_step=%ss", sample_rate, time_step)
    sim_start = time.time()

    flight = ROCKETS[cfg.rocket](
        ctrl, sample_rate=sample_rate, time_step=time_step
    )

    drogue_time = main_time = None
    for t, chute in flight.parachute_events:
        if "drogue" in chute.name.lower() and drogue_time is None:
            drogue_time = t
        if "main" in chute.name.lower() and main_time is None:
            main_time = t

    log.info("APOGEE %.4f %.4f", flight.apogee - flight.env.elevation, flight.apogee_time)
    log.info("DROGUE %.4f", drogue_time if drogue_time is not None else -1.0)
    log.info("MAIN %.4f",   main_time  if main_time  is not None else -1.0)
    log.info("WALL_TIME %.4f", time.time() - sim_start)

if __name__ == "__main__":
    main()