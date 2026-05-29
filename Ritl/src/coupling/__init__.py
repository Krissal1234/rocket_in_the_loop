from .base import CouplingStrategy
from .lockstep import LockstepCoupling
from .snapshot import SnapshotCoupling

# Maps config.arch strings to coupling classes.
COUPLING_STRATEGIES: dict[str, type[CouplingStrategy]] = {
    "lockstep":     LockstepCoupling,
    "snapshot":     SnapshotCoupling,
}
