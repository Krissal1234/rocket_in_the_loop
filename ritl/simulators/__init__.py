from .rocketpy.driver import RocketPyDriver
from .fmu.driver import FmuDriver

SIMULATOR_DRIVERS = {
    "rocketpy": RocketPyDriver,
    "fmu": FmuDriver,
}