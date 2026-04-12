import struct
from dataclasses import dataclass, field
from enum import IntEnum

# Wire format: 1 x U8 header (cmd_id), no body for drogue/main
# Order must match F Prime's ActuationCommand serializeTo field order
_FORMAT  = ">B"
_SIZE    = struct.calcsize(_FORMAT)  # 1 byte

class CommandId(IntEnum):
    DROGUE_FIRE = 0x01
    MAIN_FIRE   = 0x02
    CONTROL     = 0x03   # not implemented yet

@dataclass
class ActuationCommand:
    cmd_id: CommandId = CommandId.DROGUE_FIRE

    @classmethod
    def from_bytes(cls, raw: bytes) -> "ActuationCommand":
        if len(raw) != _SIZE:
            raise ValueError(f"Expected {_SIZE} bytes, got {len(raw)}")
        (cmd_id_byte,) = struct.unpack(_FORMAT, raw)
        return cls(cmd_id=CommandId(cmd_id_byte))

    @classmethod
    def from_dict(cls, msg: dict) -> "ActuationCommand":
        return cls(cmd_id=CommandId(msg["cmd_id"]))

    def to_bytes(self) -> bytes:
        return struct.pack(_FORMAT, int(self.cmd_id))

    def to_dict(self) -> dict:
        return {"cmd_id": int(self.cmd_id), "name": self.cmd_id.name}

    WIRE_SIZE: int = field(default=_SIZE, init=False, repr=False)