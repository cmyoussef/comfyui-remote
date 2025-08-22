# src/comfyui_remote/ui/server_manager/dialogs/server_log_dialog.py
from __future__ import annotations

from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QCheckBox, QDialogButtonBox,
    QFileDialog, QMessageBox, QLabel
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QFont, QTextCursor

from ....connectors.comfy.server_registry import ServerRecord


class LogReaderThread(QThread):
    """Thread for reading log file"""

    contentReady = Signal(str)
    errorOccurred = Signal(str)

    def __init__(self, log_path: str, tail_lines: int = 1000):
        super().__init__()
        self._log_path = log_path
        self._tail_lines = tail_lines

    def run(self):
        try:
            path = Path(self._log_path)
            if not path.exists():
                self.errorOccurred.emit(f"Log file not found: {self._log_path}")
                return

            # Read file
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            # Get tail if file is large
            if len(lines) > self._tail_lines:
                lines = lines[-self._tail_lines:]
                content = f"[Showing last {self._tail_lines} lines]\n\n" + "".join(lines)
            else:
                content = "".join(lines)

            self.contentReady.emit(content)

        except Exception as e:
            self.errorOccurred.emit(str(e))


class ServerLogDialog(QDialog):
    """Dialog for viewing server logs"""

    def __init__(self, server: ServerRecord, parent=None):
        super().__init__(parent)
        self._server = server
        self._log_path = server.log_path
        self._reader_thread = None
        self._auto_scroll = True

        self.setWindowTitle(f"Server Log - {server.id[:8]}")
        self.resize(800, 600)

        self._setupUI()
        self._loadLog()

        # Auto-refresh for running servers
        if server.state == "running":
            self._setupAutoRefresh()

    def _setupUI(self):
        """Create the dialog UI"""
        layout = QVBoxLayout(self)

        # Info bar
        infoLayout = QHBoxLayout()
        infoLayout.addWidget(QLabel(f"Server: {self._server.base_url}"))
        infoLayout.addWidget(QLabel(f"Status: {self._server.state}"))
        infoLayout.addWidget(QLabel(f"PID: {self._server.pid}"))
        infoLayout.addStretch()
        layout.addLayout(infoLayout)

        # Log viewer
        self._logViewer = QTextEdit()
        self._logViewer.setReadOnly(True)
        self._logViewer.setFont(QFont("Consolas", 9))
        self._logViewer.setLineWrapMode(QTextEdit.NoWrap)
        layout.addWidget(self._logViewer)

        # Control bar
        controlLayout = QHBoxLayout()

        self._autoScrollCheckbox = QCheckBox("Auto-scroll")
        self._autoScrollCheckbox.setChecked(True)
        self._autoScrollCheckbox.toggled.connect(self._onAutoScrollToggled)
        controlLayout.addWidget(self._autoScrollCheckbox)

        self._wrapCheckbox = QCheckBox("Word wrap")
        self._wrapCheckbox.toggled.connect(self._onWordWrapToggled)
        controlLayout.addWidget(self._wrapCheckbox)

        controlLayout.addStretch()

        self._refreshButton = QPushButton("Refresh")
        self._refreshButton.clicked.connect(self._loadLog)
        controlLayout.addWidget(self._refreshButton)

        self._clearButton = QPushButton("Clear")
        self._clearButton.clicked.connect(self._logViewer.clear)
        controlLayout.addWidget(self._clearButton)

        self._saveButton = QPushButton("Save As...")
        self._saveButton.clicked.connect(self._saveLog)
        controlLayout.addWidget(self._saveButton)

        layout.addLayout(controlLayout)

        # Dialog buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _loadLog(self):
        """Load log content"""
        if not self._log_path:
            self._logViewer.setPlainText("No log file available")
            return

        # Stop any running thread
        if self._reader_thread and self._reader_thread.isRunning():
            self._reader_thread.quit()
            self._reader_thread.wait()

        # Start reader thread
        self._reader_thread = LogReaderThread(self._log_path)
        self._reader_thread.contentReady.connect(self._onLogLoaded)
        self._reader_thread.errorOccurred.connect(self._onLogError)
        self._reader_thread.start()

    def _onLogLoaded(self, content: str):
        """Handle loaded log content"""
        # Store cursor position if not auto-scrolling
        cursor = self._logViewer.textCursor()
        old_position = cursor.position() if not self._auto_scroll else 0

        # Update content
        self._logViewer.setPlainText(content)

        # Restore position or scroll to bottom
        if self._auto_scroll:
            self._logViewer.moveCursor(QTextCursor.End)
        else:
            cursor.setPosition(old_position)
            self._logViewer.setTextCursor(cursor)

    def _onLogError(self, error: str):
        """Handle log loading error"""
        self._logViewer.setPlainText(f"Error loading log:\n{error}")

    def _onAutoScrollToggled(self, checked: bool):
        """Handle auto-scroll toggle"""
        self._auto_scroll = checked
        if checked:
            self._logViewer.moveCursor(QTextCursor.End)

    def _onWordWrapToggled(self, checked: bool):
        """Handle word wrap toggle"""
        if checked:
            self._logViewer.setLineWrapMode(QTextEdit.WidgetWidth)
        else:
            self._logViewer.setLineWrapMode(QTextEdit.NoWrap)

    def _saveLog(self):
        """Save log to file"""
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Log File",
            f"comfyui_server_{self._server.id[:8]}.log",
            "Log Files (*.log);;Text Files (*.txt);;All Files (*.*)"
        )

        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self._logViewer.toPlainText())
                QMessageBox.information(self, "Log Saved",
                                        f"Log saved to:\n{filename}")
            except Exception as e:
                QMessageBox.critical(self, "Save Failed",
                                     f"Failed to save log:\n{e}")

    def _setupAutoRefresh(self):
        """Setup auto-refresh timer for running servers"""
        self._refreshTimer = QTimer(self)
        self._refreshTimer.timeout.connect(self._loadLog)
        self._refreshTimer.start(5000)  # Refresh every 5 seconds

    def closeEvent(self, event):
        """Clean up on close"""
        if hasattr(self, '_refreshTimer'):
            self._refreshTimer.stop()
        if self._reader_thread and self._reader_thread.isRunning():
            self._reader_thread.quit()
            self._reader_thread.wait()
        super().closeEvent(event)