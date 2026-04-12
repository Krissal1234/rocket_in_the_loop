import struct
from dataclasses import dataclass, field

# Wire format: 8 F64 big-endian
# rder must match F Prime's SensorData deserializeFrom field
_FORMAT  = ">8d"
_SIZE = struct.calcsize(_FORMAT)  # 64 bytes

@dataclass
class SensorData:
    t:       float = 0.0
    accel_x: float = 0.0
    accel_y: float = 0.0
    accel_z: float = 0.0
    baro:    float = 0.0
    gyro_x:  float = 0.0
    gyro_y:  float = 0.0
    gyro_z:  float = 0.0


    @classmethod
    def from_dict(cls, msg: dict) -> "SensorData":
        accel = msg.get("accel", {})
        gyro  = msg.get("gyro",  {})
        return cls(
            t       = float(msg.get("t",    0.0)),
            accel_x = float(accel.get("x",  0.0)),
            accel_y = float(accel.get("y",  0.0)),
            accel_z = float(accel.get("z",  0.0)),
            baro    = float(msg.get("baro", 0.0)),
            gyro_x  = float(gyro.get("x",  0.0)),
            gyro_y  = float(gyro.get("y",  0.0)),
            gyro_z  = float(gyro.get("z",  0.0)),
        )

    @classmethod
    def from_bytes(cls, raw: bytes) -> "SensorData":
        if len(raw) != _SIZE:
            raise ValueError(f"Expected {_SIZE} bytes, got {len(raw)}")
        fields = struct.unpack(_FORMAT, raw)
        return cls(*fields)


    def to_bytes(self) -> bytes:
        return struct.pack(
            _FORMAT,
            self.t,
            self.accel_x, self.accel_y, self.accel_z,
            self.baro,
            self.gyro_x,  self.gyro_y,  self.gyro_z,
        )

    def to_dict(self) -> dict:
        return {
            "t":    self.t,
            "baro": self.baro,
            "accel": {"x": self.accel_x, "y": self.accel_y, "z": self.accel_z},
            "gyro":  {"x": self.gyro_x,  "y": self.gyro_y,  "z": self.gyro_z},
        }

    WIRE_SIZE: int = field(default=_SIZE, init=False, repr=False)