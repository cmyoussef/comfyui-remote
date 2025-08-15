"""Theme."""
from PyQt5 import QtWidgets


class ThemeManager:
    def apply(self, widget: QtWidgets.QWidget) -> None:
        widget.setStyleSheet("")  # placeholder for QSS
