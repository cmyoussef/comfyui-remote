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
    """
    A wrapper around wsproto to provide a websocket-client-like interface
    """

    def __init__(self):
        self.ws_connection = None
        self.socket = None
        self.connected = False
        self._received_messages = []
        self._connection_established = False

    def connect(self, url: str, timeout: float = 10.0):
        """Connect to WebSocket server using wsproto"""
        try:
            # Parse WebSocket URL
            parsed = urlparse(url)
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == "wss" else 80)

            # Create socket connection
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(timeout)
            self.socket.connect((host, port))

            # Create wsproto connection
            self.ws_connection = WSConnection(ConnectionType.CLIENT)

            # Create WebSocket handshake request
            target = parsed.path
            if parsed.query:
                target += "?" + parsed.query

            request = Request(host=host, target=target)

            # Send handshake
            data_to_send = self.ws_connection.send(request)
            self.socket.send(data_to_send)

            # Wait for handshake response
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
                            logger.info("WebSocket connection established")
                            break
                        elif isinstance(event, CloseConnection):
                            raise ConnectionError(
                                f"Connection rejected: {event.code} {event.reason}"
                            )
                        # Handle potential early pings (unlikely but robust)
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
        """Send text message"""
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
        """Receive message (blocking)"""
        if not self.connected or not self.ws_connection:
            raise ConnectionError("WebSocket not connected")

        # Check if we have buffered messages
        if self._received_messages:
            return self._received_messages.pop(0)

        # Set socket timeout
        original_timeout = self.socket.gettimeout()
        if timeout is not None:
            self.socket.settimeout(timeout)

        try:
            while self.connected:
                # Use select for non-blocking check with timeout
                ready = select.select([self.socket], [], [], timeout or 1.0)[0]

                if not ready:
                    if timeout is not None:
                        raise TimeoutError("Receive timeout")
                    continue  # Continue loop if no timeout specified

                data = self.socket.recv(4096)
                if not data:
                    self.connected = False
                    raise ConnectionError("Connection closed by server")

                self.ws_connection.receive_data(data)

                # Process ALL events from the data
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
                        pass  # Ignore unsolicited pongs
                    elif isinstance(event, CloseConnection):
                        self.connected = False
                        raise ConnectionError(
                            f"Connection closed: {event.code} {event.reason or ''}"
                        )

                # Return the first buffered message if available
                if self._received_messages:
                    return self._received_messages.pop(0)

        except Exception as e:
            if "timeout" not in str(e).lower():
                self.connected = False
            raise e
        finally:
            # Restore original timeout
            self.socket.settimeout(original_timeout)

    def close(self):
        """Close WebSocket connection"""
        if self.ws_connection and self.connected:
            try:
                # Send close frame
                close_event = CloseConnection(code=1000)  # Normal closure
                close_data = self.ws_connection.send(close_event)
                if close_data and self.socket:
                    self.socket.send(close_data)

                # Wait for close response
                start_time = time.time()
                while (
                    self.connected and (time.time() - start_time) < 5.0
                ):  # 5 second timeout
                    ready = select.select([self.socket], [], [], 0.1)
                    if ready[0]:
                        data = self.socket.recv(1024)
                        if data:
                            self.ws_connection.receive_data(data)
                            for event in self.ws_connection.events():
                                if isinstance(event, CloseConnection):
                                    self.connected = False
                                    break
                                # Handle any final events
                                elif isinstance(event, Ping):
                                    self.socket.send(
                                        self.ws_connection.send(Pong(event.payload))
                                    )
                                elif isinstance(event, Pong):
                                    pass
                        else:
                            break

            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                logger.debug(f"WebSocket close interrupted by server termination: {e}")
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
