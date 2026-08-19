from abc import ABC, abstractmethod
from dataclasses import dataclass
import numpy as np
import matplotlib.pyplot as plt
from ritl.bridge.client import BridgeClient

@dataclass
class SimulationResult:
    t: np.ndarray
    altitude: np.ndarray
    vz: np.ndarray
    apogee: float
    apogee_time: float
    drogue_time: float | None
    main_time: float | None
    wall_time_s: float

    def save(self, base: str) -> None:
      np.savetxt(
          f"{base}_trajectory.csv",
          np.column_stack([self.t, self.altitude, self.vz]),
          delimiter=",", header="t,altitude_agl_m,vz_ms", comments="",
      )

    def plot(self, base: str) -> None:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
        ax1.plot(self.t, self.altitude); ax1.set_ylabel("altitude AGL (m)")
        ax2.plot(self.t, self.vz); ax2.set_ylabel("vz (m/s)"); ax2.set_xlabel("t (s)")
        fig.savefig(f"{base}_kinematics.png", dpi=150, bbox_inches="tight")
        plt.close(fig)

class SimulatorDriver(ABC):
    """Drives a native simulation to completion, talking to SimBridge through
    a BridgeClient. Owns its own execution model: callback-driven, step-
    driven, whatever """

    @abstractmethod
    def run(self, bridge_client: BridgeClient) -> SimulationResult: ...