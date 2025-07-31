import logging
import select
import socket
import time
from typing import Optional
from urllib.parse import urlparse

from wsproto import WSConnection, ConnectionType
from wsproto.events import (
    Request,
    AcceptConnection,
    CloseConnection,
    Ping,
    Pong,
    TextMessage,
    BytesMessage,
)

logger = logging.getLogger(__name__)


class WSProtoWrapper:
    """A wrapper around wsproto to provide a websocket-client-like interface.

    This class implements a simple WebSocket client using the wsproto library,
    providing methods similar to the websocket-client library for sending and
    receiving messages over WebSocket connections.
    """

    def __init__(self):
        self.ws_connection = None
        self.socket = None
        self.connected = False
        self._received_messages = []
        self._connection_established = False

    def connect(self, url: str, timeout: float = 10.0):
        """Connect to WebSocket server using wsproto.

        Args:
            url: WebSocket URL to connect to (ws:// or wss://)
            timeout: Connection timeout in seconds

        Raises:
            ConnectionError: If connection fails or is rejected
            TimeoutError: If handshake times out
        """
        try:
            parsed = urlparse(url)
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == "wss" else 80)

            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(timeout)
            self.socket.connect((host, port))

            self.ws_connection = WSConnection(ConnectionType.CLIENT)

            target = parsed.path
            if parsed.query:
                target += "?" + parsed.query

            request = Request(host=host, target=target)

            data_to_send = self.ws_connection.send(request)
            self.socket.send(data_to_send)

            start_time = time.time()
            while (
                not self._connection_established
                and (time.time() - start_time) < timeout
            ):
                ready = select.select([self.socket], [], [], 0.1)
                if ready[0]:
                    data = self.socket.recv(4096)
                    if not data:
                        raise ConnectionError("Connection closed during handshake")

                    self.ws_connection.receive_data(data)

                    for event in self.ws_connection.events():
                        if isinstance(event, AcceptConnection):
                            self._connection_established = True
                            self.connected = True
                            break
                        elif isinstance(event, CloseConnection):
                            raise ConnectionError(
                                f"Connection rejected: {event.code} {event.reason}"
                            )
                        elif isinstance(event, Ping):
                            self.socket.send(
                                self.ws_connection.send(Pong(event.payload))
                            )
                        elif isinstance(event, Pong):
                            pass

            if not self._connection_established:
                raise TimeoutError("WebSocket handshake timeout")

        except Exception as e:
            self.connected = False
            if self.socket:
                self.socket.close()
                self.socket = None
            raise e

    def send(self, message: str):
        """Send text message over the WebSocket connection.

        Args:
            message: Text message to send

        Raises:
            ConnectionError: If WebSocket is not connected
        """
        if not self.connected or not self.ws_connection:
            raise ConnectionError("WebSocket not connected")

        try:
            text_event = TextMessage(data=message)
            data_to_send = self.ws_connection.send(text_event)
            self.socket.send(data_to_send)
        except Exception as e:
            self.connected = False
            raise e

    def recv(self, timeout: Optional[float] = None) -> str:
        """Receive message from the WebSocket connection (blocking).

        Args:
            timeout: Optional timeout in seconds. If None, blocks indefinitely

        Returns:
            Received text message

        Raises:
            ConnectionError: If WebSocket is not connected or connection is closed
            TimeoutError: If timeout expires before receiving a message
        """
        if not self.connected or not self.ws_connection:
            raise ConnectionError("WebSocket not connected")

        if self._received_messages:
            return self._received_messages.pop(0)

        original_timeout = self.socket.gettimeout()
        if timeout is not None:
            self.socket.settimeout(timeout)

        try:
            while self.connected:
                ready = select.select([self.socket], [], [], timeout or 1.0)[0]

                if not ready:
                    if timeout is not None:
                        raise TimeoutError("Receive timeout")
                    continue

                data = self.socket.recv(4096)
                if not data:
                    self.connected = False
                    raise ConnectionError("Connection closed by server")

                self.ws_connection.receive_data(data)

                for event in self.ws_connection.events():
                    if isinstance(event, TextMessage):
                        self._received_messages.append(event.data)
                    elif isinstance(event, BytesMessage):
                        self._received_messages.append(event.data.decode("utf-8"))
                    elif isinstance(event, Ping):
                        pong_event = Pong(payload=event.payload)
                        data_to_send = self.ws_connection.send(pong_event)
                        self.socket.send(data_to_send)
                    elif isinstance(event, Pong):
                        pass
                    elif isinstance(event, CloseConnection):
                        self.connected = False
                        raise ConnectionError(
                            f"Connection closed: {event.code} {event.reason or ''}"
                        )

                if self._received_messages:
                    return self._received_messages.pop(0)

        except Exception as e:
            if "timeout" not in str(e).lower():
                self.connected = False
            raise e
        finally:
            self.socket.settimeout(original_timeout)

        raise ConnectionError("Connection lost while waiting for message")

    def close(self):
        """Close WebSocket connection gracefully with proper handshake."""
        if self.ws_connection and self.connected:
            try:
                close_event = CloseConnection(code=1000)
                close_data = self.ws_connection.send(close_event)
                if close_data and self.socket:
                    self.socket.send(close_data)

                start_time = time.time()
                while self.connected and (time.time() - start_time) < 5.0:
                    ready = select.select([self.socket], [], [], 0.1)
                    if ready[0]:
                        data = self.socket.recv(1024)
                        if data:
                            self.ws_connection.receive_data(data)
                            for event in self.ws_connection.events():
                                if isinstance(event, CloseConnection):
                                    self.connected = False
                                    break
                                elif isinstance(event, Ping):
                                    self.socket.send(
                                        self.ws_connection.send(Pong(event.payload))
                                    )
                                elif isinstance(event, Pong):
                                    pass
                        else:
                            break

            except (ConnectionResetError, BrokenPipeError, OSError):
                pass
            except Exception as e:
                logger.warning(f"Error during close handshake: {e}")
            finally:
                self.connected = False
                if self.socket:
                    self.socket.close()
                    self.socket = None
                self.ws_connection = None
                self._connection_established = False
                self._received_messages = []
