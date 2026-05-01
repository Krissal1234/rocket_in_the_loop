import socket
import threading
import logging
from models.actuation_data import ActuationCommand, CommandId

log = logging.getLogger("ritl.actuation_tcp_server")

class ActuationTcpServer:
    """TCP Server that waits on incoming actuation flags from FSW."""

    def __init__(self, host: str, port: int, flag_store):
        self._host = host
        self._port = port
        self._flag_store = flag_store
        self._server_sock = None

    def start(self) -> None:
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self._host, self._port))
        self._server_sock.listen(1)
        log.info(f"Actuation server listening on {self._host}:{self._port}")

        conn, addr = self._server_sock.accept()  # blocks until FSW connects
        log.info(f"FSW connected from {addr}")

        threading.Thread(target=self._handle_connection, # starting a background thread for listener
                         args=(conn,), daemon=True,
                         name="actuation-handler").start()

    def _handle_connection(self, conn: socket.socket) -> None:
        with conn:
            while True:
                try:
                    packet_header = conn.recv(1)
                    if not packet_header:
                        raise ConnectionResetError("Connection closed")

                    cmd_id = CommandId(packet_header[0])

                    if cmd_id == CommandId.AIRBRAKE_SET:
                        body = conn.recv(4)
                        raw = packet_header + body
                    else:
                        raw = packet_header

                    cmd = ActuationCommand.from_bytes(raw)
                    self._flag_store.actuate(cmd)

                except socket.timeout:
                    continue
                except Exception as e:
                    log.error(f"Connection error: {e}")
                    return


    def close(self) -> None:
        if self._server_sock:
            self._server_sock.close()