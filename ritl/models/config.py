from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import yaml


@dataclass
class NetworkConfig:
    fsw_host: str = "127.0.0.1"
    fsw_sensor_port: int = 50100
    fsw_actuation_port: int = 50101
    zmq_address: str = "tcp://127.0.0.1:5560"


@dataclass
class FaultConfig:
    enabled: bool = False
    dropout_rate: float = 0.0
    freeze_baro: bool = False
    freeze_baro_at: float = 0.0


@dataclass
class RocketPyConfig:
    rocket: str = "cameos"
    arch: Optional[str] = None          # blocking | non_blocking (only meaningful if the rocket has airbrakes or TVC in the future)
    max_time_step: float = 0.001
    min_time_step: float = 0.001


@dataclass
class FmuConfig:
    path: str = ""
    step_size: float = 0.01
    stop_time: float = 60.0
    outputs: dict = field(default_factory=dict)   # SensorData field
    inputs: dict = field(default_factory=dict) # ActuationData field



@dataclass
class RitlConfig:
    mode: str = "sil"                    # sil | nonsil
    simulator: str = "rocketpy"          # rocketpy | fmu
    run_id: Optional[str] = None
    log_dir: str = "logs"

    network: NetworkConfig = field(default_factory=NetworkConfig)
    fault: FaultConfig = field(default_factory=FaultConfig)
    rocketpy: RocketPyConfig = field(default_factory=RocketPyConfig)
    fmu: FmuConfig = field(default_factory=FmuConfig)

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
    rocketpy_raw = data.pop("rocketpy", {}) or {}
    fmu_raw = data.pop("fmu", {}) or {}

    return RitlConfig(
        mode=data.get("mode", "sil"),
        simulator=data.get("simulator", "rocketpy"),
        run_id=data.get("run_id"),
        log_dir=data.get("log_dir", "logs"),
        network=NetworkConfig(**network_raw),
        fault=FaultConfig(**fault_raw),
        rocketpy=RocketPyConfig(**rocketpy_raw),
        fmu=FmuConfig(**fmu_raw),
    )