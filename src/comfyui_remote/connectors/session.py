"""HTTP session."""
from typing import Optional, Dict, Any
import requests


class SessionFactory:
    def __init__(self, auth: Optional[Dict[str, Any]] = None, timeout: float = 60.0) -> None:
        self._auth = auth or {}
        self._timeout = timeout

    def create(self) -> requests.Session:
        s = requests.Session()
        headers = {}
        token = self._auth.get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        s.headers.update(headers)
        s.timeout = self._timeout
        return s
