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
from config import load_config
from orchestrator.orchestrator import Orchestrator
from controllers.non_sil import NonSilControllers
from controllers.sil import SilControllers

ROCKETS = {
    "calisto": calisto.build,
    "cameos":  cameos.build,
}

def main():
    cfg = load_config("config/config.yaml")

    base = os.path.join(cfg.log_dir, f"{cfg.mode}_{cfg.arch or 'default'}_{cfg.rocket}")
    os.makedirs(cfg.log_dir, exist_ok=True)

    logging.basicConfig(
        filename=f"{base}.log",
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
    )

    log = logging.getLogger("ritl")
    log.info("mode=%s  arch=%s  rocket=%s", cfg.mode, cfg.arch, cfg.rocket)

    ctx = zmq.Context.instance()

    if cfg.is_sil:
        ready = threading.Event()
        orch  = Orchestrator(ctx, cfg.network, lockstep=(cfg.arch == "lockstep"), ready_event=ready)
        ctrl  = SilControllers(ctx, cfg.network.zmq_address)
        threading.Thread(target=orch.run, name="orchestrator", daemon=True).start()
        ready.wait()
        ctrl.connect()
    else:
        ctrl = NonSilControllers()

    log.info("building flight...")
    sim_start = time.time()
    flight = ROCKETS[cfg.rocket](ctrl, enable_sil=cfg.is_sil)

    drogue_time = main_time = None
    for t, chute in flight.parachute_events:
        if "drogue" in chute.name.lower() and drogue_time is None: drogue_time = t
        if "main"   in chute.name.lower() and main_time   is None: main_time   = t

    log.info("APOGEE %.4f %.4f", flight.apogee - flight.env.elevation, flight.apogee_time)
    log.info("DROGUE %.4f", drogue_time)
    log.info("MAIN   %.4f", main_time)
    log.info("WALL_TIME %.4f", time.time() - sim_start)

    alt = np.array(flight.z.source)
    vz  = np.array(flight.vz.source)
    np.savetxt(
        f"{base}_trajectory.csv",
        np.column_stack([alt[:, 0], alt[:, 1] - flight.env.elevation, vz[:, 1]]),
        delimiter=",", header="t,altitude_agl_m,vz_ms", comments="",
    )

    flight.plots.linear_kinematics_data()
    plt.savefig(f"{base}_kinematics.png", dpi=150, bbox_inches="tight")
    plt.close("all")

    flight.plots.trajectory_3d()
    plt.savefig(f"{base}_trajectory3d.png", dpi=150, bbox_inches="tight")
    plt.close("all")


if __name__ == "__main__":
    main()
