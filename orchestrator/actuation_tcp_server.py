# actuation_server.py
import socket
import threading
import logging
from models.actuation_data import ActuationCommand, CommandId

log = logging.getLogger("ritl.actuation_tcp_server")

class ActuationTcpServer:
    def __init__(self, host: str, port: int, flag_store):
        self._host  = host
        self._port  = port
        self._flag_store = flag_store
        self._server_sock = None

        self._handlers = {
            CommandId.DROGUE_FIRE: self._handle_drogue,
            CommandId.MAIN_FIRE:   self._handle_main,
            CommandId.CONTROL:     self._handle_control,
        }

    def start(self) -> None:
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self._host, self._port))
        self._server_sock.listen(1)

        log.info(f"Actuation server listening on {self._host}:{self._port}")
        threading.Thread(target=self._accept_loop, daemon=True,
                         name="actuation-server").start()

    def _accept_loop(self) -> None:
        while True:
            try:
                conn, addr = self._server_sock.accept()
                log.info(f"FSW connected from {addr}")
                threading.Thread(target=self._handle_connection,
                                 args=(conn,), daemon=True).start()
            except Exception as e:
                log.error(f"Accept error: {e}")

    def _handle_connection(self, conn: socket.socket) -> None:
        conn.settimeout(10.0)
        with conn:
            while True:
                try:
                    raw = conn.recv(1)
                    if not raw:
                        raise ConnectionResetError("Connection closed")
                    cmd = ActuationCommand.from_bytes(raw)
                    handler = self._handlers.get(cmd.cmd_id)
                    if handler:
                        handler(cmd)
                    else:
                        log.warning(f"No handler for {cmd.cmd_id}")
                except socket.timeout:
                    continue
                except Exception as e:
                    log.error(f"Connection error: {e}")
                    return


    def _handle_drogue(self, cmd: ActuationCommand) -> None:
        log.info("DROGUE_FIRE command received")
        self._flag_store.actuate(cmd)

    def _handle_main(self, cmd: ActuationCommand) -> None:
        log.info("MAIN_FIRE command received")
        self._flag_store.actuate(cmd)

    def _handle_control(self, cmd: ActuationCommand) -> None:
        log.warning("CONTROL command received but not implemented")

    def close(self) -> None:
        if self._server_sock:
            self._server_sock.close()