from .base import CouplingStrategy
from .blocking import BlockingCoupling
from .non_blocking import NonBlockingCoupling

COUPLING_STRATEGIES: dict[str, type[CouplingStrategy]] = {
    "blocking": BlockingCoupling,
    "non_blocking": NonBlockingCoupling,
}
