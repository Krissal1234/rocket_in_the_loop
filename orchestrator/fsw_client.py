import struct
import threading
import logging
import socket


log = logging.getLogger("ritl.fsw_client")

FSW_TCP_HOST = "host.docker.internal"
FSW_TCP_PORT = 50100

# SensorData wire format: 8 x F64 big-endian
# Fields: time, accel.x, accel.y, accel.z, baro, gyro.x, gyro.y, gyro.z
SENSOR_STRUCT_FMT   = ">8d"          # 8 doubles, in big endian format
SENSOR_STRUCT_SIZE  = struct.calcsize(SENSOR_STRUCT_FMT)   # 64 bytes
ACK_BYTE            = 0x06


def pack_sensor_data(msg: dict) -> bytes:
    accel = msg.get("accel", {})
    gyro  = msg.get("gyro",  {})
    return struct.pack(
        SENSOR_STRUCT_FMT,
        float(msg.get("t",    0.0)),
        float(accel.get("x",  0.0)),
        float(accel.get("y",  0.0)),
        float(accel.get("z",  0.0)),
        float(msg.get("baro", 0.0)),
        float(gyro.get("x",   0.0)),
        float(gyro.get("y",   0.0)),
        float(gyro.get("z",   0.0)),
    )


class FswTcpClient:

    def __init__(self, host: str, port: int):
        self._host = host
        self._port = port
        self._sock = None
        self._lock = threading.Lock()

    def connect(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(5.0)
        self._sock.connect((self._host, self._port))
        log.info(f"Connected to FSW TCP server at {self._host}:{self._port}")

    def send_sensor(self, msg: dict) -> bool:
        payload = pack_sensor_data(msg)
        with self._lock:
            try:
                self._sock.sendall(payload)
                ack = self._sock.recv(1)
                if ack and ack[0] == ACK_BYTE:
                    return True
                log.warning(f"Unexpected ACK: {ack!r}")
                return False
            except socket.timeout:
                log.error("FSW TCP timeout waiting for ACK")
                return False
            except Exception as e:
                log.error(f"FSW TCP error: {e}")
                return False

    def close(self):
        if self._sock:
            self._sock.close()