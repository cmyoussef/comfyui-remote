# src/comfyui_remote/ui/server_manager/widgets/server_filters_bar.py
from __future__ import annotations

from typing import List
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QCheckBox, QLineEdit,
    QLabel, QPushButton, QComboBox
)
from PySide6.QtCore import Signal, Qt


class ServerFiltersBar(QWidget):
    """Filter bar for server list"""

    # Signals
    filtersChanged = Signal()  # Emitted when any filter changes

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setupUI()
        self._connectSignals()

    def _setupUI(self):
        """Create the filter UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Status filters
        layout.addWidget(QLabel("Show:"))

        self._runningCheckbox = QCheckBox("Running")
        self._runningCheckbox.setChecked(True)
        layout.addWidget(self._runningCheckbox)

        self._stoppedCheckbox = QCheckBox("Stopped")
        self._stoppedCheckbox.setChecked(False)
        layout.addWidget(self._stoppedCheckbox)

        layout.addSpacing(20)

        # Tag filter
        layout.addWidget(QLabel("Tags:"))
        self._tagCombo = QComboBox()
        self._tagCombo.setEditable(False)
        self._tagCombo.addItems(["All", "local", "farm", "test"])
        self._tagCombo.setMinimumWidth(100)
        layout.addWidget(self._tagCombo)

        layout.addSpacing(20)

        # Host filter
        layout.addWidget(QLabel("Host:"))
        self._hostEdit = QLineEdit()
        self._hostEdit.setPlaceholderText("Filter by hostname...")
        self._hostEdit.setMinimumWidth(150)
        layout.addWidget(self._hostEdit)

        # Clear filters button
        self._clearButton = QPushButton("Clear Filters")
        self._clearButton.clicked.connect(self.clearFilters)
        layout.addWidget(self._clearButton)

        # Stretch at the end
        layout.addStretch()

    def _connectSignals(self):
        """Connect internal signals"""
        self._runningCheckbox.toggled.connect(lambda _: self.filtersChanged.emit())
        self._stoppedCheckbox.toggled.connect(lambda _: self.filtersChanged.emit())
        self._tagCombo.currentTextChanged.connect(lambda _: self.filtersChanged.emit())
        self._hostEdit.textChanged.connect(lambda _: self.filtersChanged.emit())

    def showRunning(self) -> bool:
        """Return whether to show running servers"""
        return self._runningCheckbox.isChecked()

    def showStopped(self) -> bool:
        """Return whether to show stopped servers"""
        return self._stoppedCheckbox.isChecked()

    def getTagFilter(self) -> List[str]:
        """Get selected tag filters"""
        tag = self._tagCombo.currentText()
        if tag == "All":
            return []
        return [tag]

    def getHostFilter(self) -> str:
        """Get host filter text"""
        return self._hostEdit.text()

    def clearFilters(self):
        """Reset all filters to defaults"""
        self._runningCheckbox.setChecked(True)
        self._stoppedCheckbox.setChecked(False)
        self._tagCombo.setCurrentIndex(0)
        self._hostEdit.clear()
        self.filtersChanged.emit()

    def applyToProxyModel(self, proxy_model):
        """Apply current filters to a proxy model"""
        proxy_model.setShowRunning(self.showRunning())
        proxy_model.setShowStopped(self.showStopped())
        proxy_model.setTagFilter(self.getTagFilter())
        proxy_model.setHostFilter(self.getHostFilter())