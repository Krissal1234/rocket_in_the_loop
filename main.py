import argparse
import logging
import os
import datetime

from ritl.models.config import load_config
from ritl.models.fault_injector import FaultInjector
from ritl.adapters.fprime_adapter import FPrimeAdapter
from ritl.coupling import COUPLING_STRATEGIES
from ritl.simulators import SIMULATOR_DRIVERS
from ritl.bridge import SimBridge
from ritl.bridge.client import BridgeClient

def main():
    parser = argparse.ArgumentParser(description="Run RITL from a configuration file.")
    parser.add_argument("--config", default="configs/default.yaml", help="Path to the YAML config file")
    args = parser.parse_args()

    cfg = load_config(args.config)

    if not cfg:
        raise FileNotFoundError(f"Failed to load configuration from {args.config}")

    run_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = cfg.rocketpy.arch or "default" if cfg.simulator == "rocketpy" else "fmu"
    base = os.path.join(cfg.log_dir, f"{cfg.mode}_{cfg.simulator}_{tag}_{run_timestamp}")
    os.makedirs(cfg.log_dir, exist_ok=True)

    # Logging setup
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    file_fmt = logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s")
    file_handler = logging.FileHandler(f"{base}.log", mode="w")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_fmt)

    console_fmt = logging.Formatter("[%(levelname)s] %(message)s")
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_fmt)

    root.addHandler(file_handler)
    root.addHandler(console_handler)

    log = logging.getLogger("ritl")
    log.info("Initializing RITL execution | mode=%s simulator=%s", cfg.mode, cfg.simulator)

    fault_injector = (
        FaultInjector(cfg.fault.freeze_baro, cfg.fault.freeze_baro_at, cfg.fault.dropout_rate)
        if cfg.fault.enabled else None
    )

    if cfg.fault.enabled:
        log.warning("Fault injection active: dropout_rate=%.2f", cfg.fault.dropout_rate)

    bridge_client = None
    if cfg.is_sil:
        if cfg.simulator == "rocketpy":
            arch = cfg.rocketpy.arch or "blocking"
            if arch not in COUPLING_STRATEGIES:
                raise ValueError(f"Unknown arch '{arch}'. Valid: {list(COUPLING_STRATEGIES)}")
            coupling = COUPLING_STRATEGIES[arch]()
        else:
            coupling = COUPLING_STRATEGIES["blocking"]()  # fmu: not exposed ylet

        fsw = FPrimeAdapter(cfg.network)
        bridge = SimBridge(fsw, coupling, cfg.network.zmq_address, fault_injector)

        log.info("Waiting for F Prime handshake on sensor/actuation ports...")
        bridge.start_async()  # connects to FSW + binds ZMQ, then returns

        bridge_client = BridgeClient(cfg.network.zmq_address)

    log.info("Building and executing %s driver...", cfg.simulator)
    driver = SIMULATOR_DRIVERS[cfg.simulator](cfg.is_sil, cfg.rocketpy.rocket)
    result = driver.run(bridge_client)


    if cfg.is_sil:
        bridge.save_telemetry(base)
        bridge.stop()
        bridge_client.close()
        if bridge_client:
            bridge_client.close()

    log.info("=== FLIGHT SIMULATION RESULTS ===")
    log.info("APOGEE     %.4f m @ %.4f s", result.apogee, result.apogee_time)
    log.info("DROGUE     %.4f s", result.drogue_time if result.drogue_time is not None else -1.0)
    log.info("MAIN       %.4f s", result.main_time if result.main_time is not None else -1.0)
    log.info("WALL_TIME  %.4f s", result.wall_time_s)

    log.info("Artifacts successfully saved to %s.*", base)

if __name__ == "__main__":
    main()