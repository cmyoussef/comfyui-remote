# src/comfyui_remote/ui/server_manager/dialogs/start_server_dialog.py
from __future__ import annotations

import socket
from typing import Dict, Any
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QPushButton, QCheckBox,
    QDialogButtonBox, QFileDialog, QGroupBox,
    QComboBox, QLabel, QRadioButton, QButtonGroup
)
from PySide6.QtCore import Qt


class StartServerDialog(QDialog):
    """Dialog for starting a new ComfyUI server"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Start ComfyUI Server")
        self.setModal(True)
        self.resize(500, 450)

        self._setupUI()
        self._loadDefaults()

    def _setupUI(self):
        """Create the dialog UI"""
        layout = QVBoxLayout(self)

        # Server Type Selection
        typeGroup = QGroupBox("Server Type")
        typeLayout = QVBoxLayout()

        self._serverTypeGroup = QButtonGroup()

        self._localRadio = QRadioButton("Local Server (this machine)")
        self._localRadio.setChecked(True)
        self._localRadio.setToolTip("Start a server on this machine with specified settings")
        self._serverTypeGroup.addButton(self._localRadio, 0)
        typeLayout.addWidget(self._localRadio)

        self._farmRadio = QRadioButton("Farm Server (distributed/remote)")
        self._farmRadio.setToolTip("Register a farm server that will be started by a farm manager")
        self._serverTypeGroup.addButton(self._farmRadio, 1)
        typeLayout.addWidget(self._farmRadio)

        # Connect to update UI based on selection
        self._serverTypeGroup.buttonClicked.connect(self._onServerTypeChanged)

        typeGroup.setLayout(typeLayout)
        layout.addWidget(typeGroup)

        # Server settings group
        serverGroup = QGroupBox("Server Settings")
        serverLayout = QFormLayout()

        # Host
        self._hostEdit = QLineEdit()
        self._hostEdit.setText("127.0.0.1")
        self._hostEdit.setPlaceholderText("Server host address")
        self._hostLabel = QLabel("Host:")
        serverLayout.addRow(self._hostLabel, self._hostEdit)

        # Port with find button
        portLayout = QHBoxLayout()
        self._portSpinBox = QSpinBox()
        self._portSpinBox.setRange(0, 65535)
        self._portSpinBox.setValue(0)  # 0 means auto-select
        self._portSpinBox.setSpecialValueText("Auto")
        self._portSpinBox.setToolTip("0 = automatically select free port")
        portLayout.addWidget(self._portSpinBox)

        self._findPortButton = QPushButton("Find Free Port")
        self._findPortButton.clicked.connect(self._onFindFreePort)
        self._findPortButton.setMaximumWidth(100)
        portLayout.addWidget(self._findPortButton)
        portLayout.addStretch()

        serverLayout.addRow("Port:", portLayout)

        # Custom tag (optional)
        self._tagEdit = QLineEdit()
        self._tagEdit.setPlaceholderText("Optional custom tag (e.g., 'test', 'production')")
        serverLayout.addRow("Tag:", self._tagEdit)

        serverGroup.setLayout(serverLayout)
        layout.addWidget(serverGroup)

        # Directory settings group
        self._dirGroup = QGroupBox("Directory Settings (Optional)")
        dirLayout = QFormLayout()

        # Input directory
        self._inputDirEdit = QLineEdit()
        self._inputDirEdit.setPlaceholderText("Leave empty for default")
        inputBrowse = QPushButton("Browse...")
        inputBrowse.clicked.connect(lambda: self._browseDirectory(self._inputDirEdit))
        inputLayout = QHBoxLayout()
        inputLayout.addWidget(self._inputDirEdit)
        inputLayout.addWidget(inputBrowse)
        dirLayout.addRow("Input Dir:", inputLayout)

        # Output directory
        self._outputDirEdit = QLineEdit()
        self._outputDirEdit.setPlaceholderText("Leave empty for default")
        outputBrowse = QPushButton("Browse...")
        outputBrowse.clicked.connect(lambda: self._browseDirectory(self._outputDirEdit))
        outputLayout = QHBoxLayout()
        outputLayout.addWidget(self._outputDirEdit)
        outputLayout.addWidget(outputBrowse)
        dirLayout.addRow("Output Dir:", outputLayout)

        # Temp directory
        self._tempDirEdit = QLineEdit()
        self._tempDirEdit.setPlaceholderText("Leave empty for default")
        tempBrowse = QPushButton("Browse...")
        tempBrowse.clicked.connect(lambda: self._browseDirectory(self._tempDirEdit))
        tempLayout = QHBoxLayout()
        tempLayout.addWidget(self._tempDirEdit)
        tempLayout.addWidget(tempBrowse)
        dirLayout.addRow("Temp Dir:", tempLayout)

        # User directory
        self._userDirEdit = QLineEdit()
        self._userDirEdit.setPlaceholderText("Leave empty for default")
        userBrowse = QPushButton("Browse...")
        userBrowse.clicked.connect(lambda: self._browseDirectory(self._userDirEdit))
        userLayout = QHBoxLayout()
        userLayout.addWidget(self._userDirEdit)
        userLayout.addWidget(userBrowse)
        dirLayout.addRow("User Dir:", userLayout)

        self._dirGroup.setLayout(dirLayout)
        layout.addWidget(self._dirGroup)

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _onServerTypeChanged(self, button):
        """Handle server type change"""
        is_local = (button == self._localRadio)

        if is_local:
            # Local server settings
            self._hostEdit.setText("127.0.0.1")
            self._hostEdit.setEnabled(True)
            self._hostLabel.setText("Host:")
            self._portSpinBox.setEnabled(True)
            self._findPortButton.setEnabled(True)
            self._dirGroup.setEnabled(True)
            self._tagEdit.setText("")
        else:
            # Farm server settings
            self._hostEdit.setText("")
            self._hostEdit.setPlaceholderText("Will be assigned by farm manager")
            self._hostEdit.setEnabled(False)
            self._hostLabel.setText("Host (auto):")
            self._portSpinBox.setValue(0)
            self._portSpinBox.setEnabled(False)
            self._findPortButton.setEnabled(False)
            self._dirGroup.setEnabled(False)
            self._tagEdit.setText("farm")

    def _onFindFreePort(self):
        """Find and set a free port"""
        try:
            # Get the host to bind to
            host = self._hostEdit.text() or "127.0.0.1"

            # Find a free port
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((host, 0))
                port = s.getsockname()[1]

            # Set the port value
            self._portSpinBox.setValue(port)

        except Exception as e:
            # If binding fails, try localhost
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("127.0.0.1", 0))
                    port = s.getsockname()[1]
                self._portSpinBox.setValue(port)
            except Exception:
                # Fall back to a common range
                import random
                self._portSpinBox.setValue(random.randint(8000, 9000))

    def _loadDefaults(self):
        """Load default values from environment or config"""
        import os

        # Check environment variables for local server
        if os.getenv("COMFY_LISTEN"):
            self._hostEdit.setText(os.getenv("COMFY_LISTEN"))
        if os.getenv("COMFY_PORT"):
            try:
                port = int(os.getenv("COMFY_PORT"))
                self._portSpinBox.setValue(port)
            except ValueError:
                pass

        # Check for default directories
        if os.getenv("COMFY_INPUT"):
            self._inputDirEdit.setText(os.getenv("COMFY_INPUT"))
        if os.getenv("COMFY_OUTPUT"):
            self._outputDirEdit.setText(os.getenv("COMFY_OUTPUT"))
        if os.getenv("COMFY_TEMP"):
            self._tempDirEdit.setText(os.getenv("COMFY_TEMP"))
        if os.getenv("COMFY_USER"):
            self._userDirEdit.setText(os.getenv("COMFY_USER"))

    def _browseDirectory(self, lineEdit: QLineEdit):
        """Browse for directory"""
        current = lineEdit.text() or str(Path.home())
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Directory",
            current,
            QFileDialog.ShowDirsOnly
        )
        if directory:
            lineEdit.setText(directory)

    def getOptions(self) -> Dict[str, Any]:
        """Get the configured options"""
        is_farm = self._farmRadio.isChecked()

        options = {}

        if is_farm:
            # Farm server - minimal options, will be configured by farm manager
            options["tags"] = ["farm"]
            # Add custom tag if provided
            if self._tagEdit.text() and self._tagEdit.text() != "farm":
                options["tags"].append(self._tagEdit.text())
            # Farm manager will assign host/port when it actually starts the server
            # We're just registering the intent to have a farm server
            options["meta"] = {"type": "farm", "pending": True}
        else:
            # Local server - full configuration
            options["host"] = self._hostEdit.text() or "127.0.0.1"
            options["port"] = self._portSpinBox.value()

            # Add tag
            if self._tagEdit.text():
                options["tags"] = [self._tagEdit.text()]
            else:
                options["tags"] = ["local"]

            # Add directories if specified
            if self._inputDirEdit.text():
                options["input_dir"] = self._inputDirEdit.text()
            if self._outputDirEdit.text():
                options["output_dir"] = self._outputDirEdit.text()
            if self._tempDirEdit.text():
                options["temp_dir"] = self._tempDirEdit.text()
            if self._userDirEdit.text():
                options["user_dir"] = self._userDirEdit.text()

        return options