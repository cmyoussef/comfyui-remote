# src/comfyui_remote/ui/server_manager/widgets/server_actions_bar.py
from __future__ import annotations

from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel,
    QSpinBox, QCheckBox
)
from PySide6.QtCore import Signal, QTimer
from PySide6.QtGui import QIcon


class ServerActionsBar(QWidget):
    """Action bar for server operations"""

    # Signals
    startServerClicked = Signal()
    stopServerClicked = Signal()
    refreshClicked = Signal()
    viewLogsClicked = Signal()
    autoRefreshToggled = Signal(bool)
    refreshIntervalChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setupUI()
        self._updateButtonStates()

    def _setupUI(self):
        """Create the actions UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Start server button
        self._startButton = QPushButton("Start Server")
        self._startButton.setToolTip("Start a new ComfyUI server")
        self._startButton.clicked.connect(self.startServerClicked.emit)
        layout.addWidget(self._startButton)

        # Stop server button
        self._stopButton = QPushButton("Stop Server")
        self._stopButton.setToolTip("Stop selected server(s)")
        self._stopButton.clicked.connect(self.stopServerClicked.emit)
        self._stopButton.setEnabled(False)
        layout.addWidget(self._stopButton)

        # View logs button
        self._viewLogsButton = QPushButton("View Logs")
        self._viewLogsButton.setToolTip("View server logs")
        self._viewLogsButton.clicked.connect(self.viewLogsClicked.emit)
        self._viewLogsButton.setEnabled(False)
        layout.addWidget(self._viewLogsButton)

        layout.addSpacing(20)

        # Refresh button
        self._refreshButton = QPushButton("Refresh")
        self._refreshButton.setToolTip("Refresh server list")
        self._refreshButton.clicked.connect(self.refreshClicked.emit)
        layout.addWidget(self._refreshButton)

        # Auto-refresh controls
        self._autoRefreshCheckbox = QCheckBox("Auto-refresh")
        self._autoRefreshCheckbox.setChecked(True)
        self._autoRefreshCheckbox.toggled.connect(self._onAutoRefreshToggled)
        layout.addWidget(self._autoRefreshCheckbox)

        self._intervalSpinBox = QSpinBox()
        self._intervalSpinBox.setRange(1, 60)
        self._intervalSpinBox.setValue(5)
        self._intervalSpinBox.setSuffix(" sec")
        self._intervalSpinBox.setToolTip("Auto-refresh interval")
        self._intervalSpinBox.valueChanged.connect(self._onIntervalChanged)
        layout.addWidget(self._intervalSpinBox)

        layout.addSpacing(20)

        # Server count label
        self._countLabel = QLabel("Servers: 0")
        layout.addWidget(self._countLabel)

        # Stretch at the end
        layout.addStretch()

    def _onAutoRefreshToggled(self, checked: bool):
        """Handle auto-refresh toggle"""
        self._intervalSpinBox.setEnabled(checked)
        self.autoRefreshToggled.emit(checked)

    def _onIntervalChanged(self, value: int):
        """Handle interval change"""
        self.refreshIntervalChanged.emit(value * 1000)  # Convert to milliseconds

    def setServerCount(self, count: int):
        """Update server count display"""
        self._countLabel.setText(f"Servers: {count}")

    def setSelectionCount(self, count: int):
        """Update button states based on selection"""
        has_selection = count > 0
        self._stopButton.setEnabled(has_selection)
        self._viewLogsButton.setEnabled(has_selection)

        if count > 1:
            self._stopButton.setText(f"Stop {count} Servers")
        else:
            self._stopButton.setText("Stop Server")

    def _updateButtonStates(self):
        """Update button enabled states"""
        # This will be called when selection changes
        pass

    def isAutoRefreshEnabled(self) -> bool:
        """Check if auto-refresh is enabled"""
        return self._autoRefreshCheckbox.isChecked()

    def getRefreshInterval(self) -> int:
        """Get refresh interval in milliseconds"""
        return self._intervalSpinBox.value() * 1000