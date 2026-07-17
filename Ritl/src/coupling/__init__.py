from .base import CouplingStrategy
from .blocking import BlockingCoupling
from .non_blocking import NonBlockingCoupling

# Maps config.arch strings to coupling classes.
COUPLING_STRATEGIES: dict[str, type[CouplingStrategy]] = {
    "blocking": BlockingCoupling,
    "non_blocking": NonBlockingCoupling,
}
