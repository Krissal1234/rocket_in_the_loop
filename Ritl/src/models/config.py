from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import yaml


@dataclass
class NetworkConfig:
    fsw_host: str = "host.docker.internal"
    fsw_sensor_port: int = 50100
    fsw_actuation_port: int = 50101
    zmq_address: str = "tcp://127.0.0.1:5560"

@dataclass
class FaultConfig:
    enabled: bool = False
    dropout_rate: float = 0.0
    freeze_baro: bool = False



@dataclass
class RitlConfig:
    mode: str = "nonsil"          # sil | nonsil
    rocket: str = "cameos"
    arch: Optional[str] = None    # lockstep | nolockstep  (sil only)
    run_id: Optional[str] = None
    log_dir: str = "logs"
    network: NetworkConfig = field(default_factory=NetworkConfig)
    fault: FaultConfig = field(default_factory=FaultConfig)


    @property
    def is_sil(self) -> bool:
        return self.mode == "sil"


def load_config(path: str = "config/config.yaml") -> RitlConfig:
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return RitlConfig()

    network_raw = data.pop("network", {}) or {}
    fault_raw = data.pop("fault_injection", {}) or {}

    return RitlConfig(
        mode=data.get("mode", "nonsil"),
        rocket=data.get("rocket", "cameos"),
        arch=data.get("arch"),
        run_id=data.get("run_id"),
        log_dir=data.get("log_dir", "logs"),
        network=NetworkConfig(**network_raw),
        fault = FaultConfig(**fault_raw)
    )
