"""Progress bus."""
from typing import Callable, Dict, Any


class IProgressObserver:
    def update(self, event: Dict[str, Any]) -> None: ...


class ProgressService:
    def __init__(self) -> None:
        self._observers = set()

    def subscribe(self, cb: Callable[[Dict[str, Any]], None]) -> None:
        self._observers.add(cb)

    def unsubscribe(self, cb: Callable[[Dict[str, Any]], None]) -> None:
        self._observers.discard(cb)

    def publish(self, event: Dict[str, Any]) -> None:
        for cb in list(self._observers):
            try: cb(event)
            except Exception: pass


class ProgressEventAdapter(IProgressObserver):
    def update(self, event: Dict[str, Any]) -> None:
        # default no-op adapter
        pass
