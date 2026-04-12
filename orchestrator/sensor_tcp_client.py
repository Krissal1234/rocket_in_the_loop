import struct
import threading
import logging
import socket
from models.sensor_data import SensorData

log = logging.getLogger("ritl.fsw_client")

ACK_BYTE = 0x06

class FswTcpClient:
# TCP client that connects with FPrime TCP server to send Sensor Data and wait for ACK back.

    def __init__(self, host: str, port: int):
        self._host = host
        self._port = port
        self._sock = None
        self._lock = threading.Lock()

    def connect(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(2.0)
        self._sock.connect((self._host, self._port))
        log.info(f"Connected to FSW TCP server at {self._host}:{self._port}")

    def send_sensor(self, sensor: SensorData) -> bool:
        payload = sensor.to_bytes()
        with self._lock:
            try:
                self._sock.sendall(payload)
                ack = self._sock.recv(1)
                return (ack and ack[0] == ACK_BYTE)
            except socket.timeout:
                log.error("FSW TCP timeout waiting for ACK")
                return False
            except Exception as e:
                log.error(f"FSW TCP error: {e}")
                return False

    def close(self):
        if self._sock:
            self._sock.close()