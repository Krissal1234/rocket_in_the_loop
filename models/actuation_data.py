import struct
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

class CommandId(IntEnum):
    DROGUE_FIRE  = 0x01
    MAIN_FIRE    = 0x02
    AIRBRAKE_SET = 0x03

# parachute deployments - 1 byte
_HEADER_FORMAT = ">B"
_HEADER_SIZE   = struct.calcsize(_HEADER_FORMAT)

# airbrake body — 1 float deployment level 0.0 - 1.0
_AIRBRAKE_FORMAT = ">Bf"
_AIRBRAKE_SIZE   = struct.calcsize(_AIRBRAKE_FORMAT)

@dataclass
class ActuationCommand:
    cmd_id:           CommandId
    deployment_level: Optional[float] = 0.0  # only for AIRBRAKE_SET

    @classmethod
    def from_bytes(cls, raw: bytes) -> "ActuationCommand":
        if len(raw) == _HEADER_SIZE:
            (cmd_id_byte,) = struct.unpack(_HEADER_FORMAT, raw)
            return cls(cmd_id=CommandId(cmd_id_byte))
        elif len(raw) == _AIRBRAKE_SIZE:
            cmd_id_byte, level = struct.unpack(_AIRBRAKE_FORMAT, raw)
            return cls(cmd_id=CommandId(cmd_id_byte), deployment_level=level)
        else:
            raise ValueError(f"Unexpected size {len(raw)}")
