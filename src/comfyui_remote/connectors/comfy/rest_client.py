"""REST client."""
from __future__ import annotations
import requests
from ..session import SessionFactory
from typing import Optional, Dict, Any

class ComfyRestClient:
    def __init__(self, base_url: str, auth: Optional[Dict[str, Any]] = None, timeout: float = 60.0):
        self._base = base_url.rstrip("/")
        self._session = SessionFactory(auth=auth, timeout=timeout).create()
        self._timeout = timeout

    def get(self, endpoint: str):
        r = self._session.get(self._base + endpoint, timeout=self._timeout)
        r.raise_for_status()
        return r.json()

    def get_bytes(self, url: str) -> bytes:
        r = self._session.get(url, timeout=self._timeout)
        r.raise_for_status()
        return r.content

    def post(self, endpoint: str, json):
        r = self._session.post(self._base + endpoint, json=json, timeout=self._timeout)
        if r.status_code >= 400:
            # surface the server's explanation
            try:
                detail = r.json()
            except Exception:
                detail = r.text
            raise requests.HTTPError(
                f"{r.status_code} Client Error for {self._base+endpoint}: {detail}",
                response=r,
            )
        r.raise_for_status()
        return r.json()

    def set_timeout(self, timeout: float) -> None:
        self._timeout = timeout