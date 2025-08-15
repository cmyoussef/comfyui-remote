"""Net utils."""
import socket


def port_open(host: str, port: int, timeout: float = 0.2) -> bool:
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True
    except Exception:
        return False
    finally:
        s.close()
