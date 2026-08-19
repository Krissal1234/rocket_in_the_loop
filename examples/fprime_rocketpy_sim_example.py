import logging
from time import sleep
from ritl.models.config import NetworkConfig
from ritl.models.fault_injector import FaultInjector
from ritl.adapters.fprime_adapter import FPrimeAdapter
from ritl.coupling import COUPLING_STRATEGIES
from ritl.simulators import SIMULATOR_DRIVERS
from ritl.bridge import SimBridge
from ritl.bridge.client import BridgeClient

def run_custom_simulation(dropout_rate: float):
    """Runs a single simulation. Ensure you have F Prime running, with matching IP, port and packet format"""
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("ritl_api")

    # Define network & fault settings
    net_cfg = NetworkConfig(
        fsw_host="127.0.0.1",
        fsw_sensor_port=50100,
        fsw_actuation_port=50101,
        zmq_address="tcp://127.0.0.1:5560"
    )

    fault_injector = FaultInjector(
        freeze_baro=False,
        freeze_baro_at=0.0,
        dropout_rate=dropout_rate
    )

    coupling = COUPLING_STRATEGIES["non_blocking"]() # Define coupling strategy (nonblocking or blocking)
    fsw = FPrimeAdapter(net_cfg) # Define flight software framework - fprime here

    # Instantiate the bridge that connects simulator to flight software with its friendly client :)
    bridge = SimBridge(fsw, coupling, net_cfg.zmq_address, fault_injector)
    log.info("Starting Bridge...")
    bridge.start_async()

    # Connect client and run driver
    bridge_client = BridgeClient(net_cfg.zmq_address)
    bridge_client.connect()

    try:
        driver = SIMULATOR_DRIVERS["rocketpy"](is_sil=True, rocket = "calisto")
        result = driver.run(bridge_client)
    finally:
        bridge.stop()
        bridge_client.close()

    log.info("APOGEE %.4f %.4f", result.apogee, result.apogee_time)
    log.info("DROGUE %.4f", result.drogue_time if result.drogue_time is not None else -1.0)
    log.info("MAIN %.4f", result.main_time if result.main_time is not None else -1.0)
    log.info("WALL_TIME %.4f", result.wall_time_s)

if __name__ == "__main__":
        run_custom_simulation(dropout_rate=0)