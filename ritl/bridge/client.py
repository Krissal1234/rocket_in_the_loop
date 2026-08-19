import logging
import zmq
from ritl.models.actuation_data import ActuationData
from ritl.models.sensor_data import SensorData

log = logging.getLogger("ritl.bridge_client")
_ZMQ_TIMEOUT_MS = 8000

class BridgeClient:
    """Thin ZMQ REQ client speaking SimBridge's SENSOR/DROGUE_POLL/MAIN_POLL
    protocol."""

    def __init__(self, zmq_address: str):
        self._address = zmq_address
        self._socket: zmq.Socket | None = None

    def connect(self) -> None:
        ctx = zmq.Context.instance()
        self._socket = ctx.socket(zmq.REQ)
        self._socket.setsockopt(zmq.RCVTIMEO, _ZMQ_TIMEOUT_MS)
        self._socket.connect(self._address)
        log.info("BridgeClient connected to SimBridge at %s", self._address)

    def close(self) -> None:
        if self._socket:
            self._socket.close()
            self._socket = None

    def send_sensor(self, sensor: SensorData) -> ActuationData:
        raw_dict = self._send({"type": "SENSOR", **sensor.to_dict()})

        return ActuationData(
            airbrake_dep_level=raw_dict.get("airbrake_dep_level", 0.0),
            drogue=raw_dict.get("drogue", False),
            main=raw_dict.get("main", False)
        )

    def poll_drogue(self) -> bool:
        return bool(self._send({"type": "DROGUE_POLL"}).get("drogue", False))

    def poll_main(self) -> bool:
        return bool(self._send({"type": "MAIN_POLL"}).get("main", False))

    def _send(self, data: dict) -> dict:
        self._socket.send_json(data)
        return self._socket.recv_json()