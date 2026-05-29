import logging
import threading
import socket
import time

from adapters.base import FswAdapter
from models.sensor_data import SensorData
from models.actuation_data import ActuationCommand
from models.flag_store import FlagStore
from models.config import NetworkConfig

log = logging.getLogger("ritl.adapters.fprime")

_ACK_BYTE = 0x06


class _SensorTcpClient:
    """Connects to F Prime's incoming sensor port and pushes sensor packets."""

    def __init__(self, host: str, port: int):
        self._host = host
        self._port = port
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        while True:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(2.0)
            try:
                log.info("Connecting to F Prime sensor port %s:%d...", self._host, self._port)
                self._sock.connect((self._host, self._port))
                self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                log.info("Sensor TCP connected")
                break
            except Exception as exc:
                log.error("Sensor TCP connect failed (%s), retrying in 2s...", exc)
                self._sock.close()
                time.sleep(2)

    def send(self, sensor: SensorData) -> bool:
        with self._lock:
            try:
                self._sock.sendall(sensor.to_bytes())
                ack = self._sock.recv(1)
                return bool(ack and ack[0] == _ACK_BYTE)
            except socket.timeout:
                log.error("Sensor TCP: timeout waiting for ACK")
                return False
            except Exception as exc:
                log.error("Sensor TCP error: %s", exc)
                return False

    def close(self) -> None:
        if self._sock:
            self._sock.close()


class _ActuationTcpServer:
    """Accepts one connection from F Prime and writes actuation commands to FlagStore."""

    def __init__(self, port: int, flag_store: FlagStore):
        self._port = port
        self._flag_store = flag_store
        self._server_sock: socket.socket | None = None

    def start(self) -> None:
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind(("0.0.0.0", self._port))
        self._server_sock.listen(1)
        log.info("Actuation TCP server listening on port %d", self._port)
        conn, addr = self._server_sock.accept()  # blocks until F Prime connects
        log.info("F Prime actuation client connected from %s", addr)
        threading.Thread(
            target=self._handle, args=(conn,), daemon=True, name="actuation-handler"
        ).start()

    def _handle(self, conn: socket.socket) -> None:
        with conn:
            while True:
                try:
                    header = conn.recv(1)
                    if not header:
                        raise ConnectionResetError("F Prime closed actuation connection")
                    body = conn.recv(8)
                    self._flag_store.actuate(ActuationCommand.from_bytes(header + body))
                except socket.timeout:
                    continue
                except Exception as exc:
                    log.error("Actuation handler: %s", exc)
                    return

    def close(self) -> None:
        if self._server_sock:
            self._server_sock.close()


class FPrimeAdapter(FswAdapter):
    """FSW adapter for NASA F Prime over TCP.

    Sensor data --> ``fsw_sensor_port``    (we connect as client to F Prime's server).
    Actuation   <-- ``fsw_actuation_port`` (F Prime connects to our server).

    """

    def __init__(self, network: NetworkConfig):
        self._flag_store = FlagStore()
        self._client = _SensorTcpClient(network.fsw_host, network.fsw_sensor_port)
        self._server = _ActuationTcpServer(network.fsw_actuation_port, self._flag_store)

    def start(self) -> None:
        self._client.connect()  # retries until F Prime sensor server is up
        self._server.start()    # blocks until F Prime connects to actuation port
        log.info("FPrimeAdapter ready")

    def send_sensor(self, data: SensorData) -> bool:
        return self._client.send(data)

    def get_snapshot(self) -> dict:
        return self._flag_store.snapshot()

    def wait_for_airbrake(self, timeout: float = 0.2) -> float:
        return self._flag_store.wait_for_airbrake(timeout)

    def stop(self) -> None:
        self._server.close()
        self._client.close()
        log.info("FPrimeAdapter stopped")
