# src/comfyui_remote/ui/server_manager/server_manager_widget.py
from __future__ import annotations

import sys
import socket
from typing import Optional, List
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QSplitter, QMessageBox,
    QInputDialog, QApplication
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer

# Import from our package structure
from ...connectors.comfy.server_manager import ComfyServerManager
from ...connectors.comfy.server_registry import ServerRegistry, ServerRecord

from .models.server_list_model import ServerListModel, ServerFilterProxyModel
from .views.server_list_view import ServerListView
from .widgets.server_filters_bar import ServerFiltersBar
from .widgets.server_actions_bar import ServerActionsBar
from .dialogs.start_server_dialog import StartServerDialog
from .dialogs.server_log_dialog import ServerLogDialog


class ValidationThread(QThread):
    """Thread for validating servers in the background"""

    validated = Signal(int)  # Number of servers marked as stopped
    finished = Signal()

    def __init__(self, registry: ServerRegistry):
        super().__init__()
        self._registry = registry

    def run(self):
        try:
            stopped_count = self._registry.validate_and_update(timeout=2.0)
            self.validated.emit(stopped_count)
        except Exception as e:
            print(f"Validation error: {e}")
        finally:
            self.finished.emit()


class ServerOperationThread(QThread):
    """Thread for server operations"""

    success = Signal(str)  # Success message
    error = Signal(str)  # Error message

    def __init__(self, operation, *args, **kwargs):
        super().__init__()
        self._operation = operation
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            result = self._operation(*self._args, **self._kwargs)
            self.success.emit(str(result))
        except Exception as e:
            self.error.emit(str(e))


class ServerManagerWidget(QWidget):
    """Main server manager widget"""

    def __init__(self, registry: Optional[ServerRegistry] = None, parent=None):
        super().__init__(parent)
        self._registry = registry or ServerRegistry()
        self._server_manager = ComfyServerManager(registry=self._registry)
        self._operation_thread = None
        self._validation_thread = None
        self._validation_in_progress = False

        self._setupUI()
        self._connectSignals()
        self._loadInitialData()

    def _setupUI(self):
        """Setup the main UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Actions bar
        self._actionsBar = ServerActionsBar()
        layout.addWidget(self._actionsBar)

        # Filters bar
        self._filtersBar = ServerFiltersBar()
        layout.addWidget(self._filtersBar)

        # Create model and proxy
        self._model = ServerListModel(self._registry)
        self._proxyModel = ServerFilterProxyModel()
        self._proxyModel.setSourceModel(self._model)

        # Server list view
        self._listView = ServerListView()
        self._listView.setModel(self._proxyModel)

        # Set default sort by Started column (newest first)
        from .models.server_list_model import ServerColumns
        self._listView.sortByColumn(ServerColumns.STARTED, Qt.DescendingOrder)

        layout.addWidget(self._listView)

        # Set window properties if standalone
        if not self.parent():
            self.setWindowTitle("ComfyUI Server Manager")
            self.resize(900, 600)

    def _connectSignals(self):
        """Connect all signals"""
        # Actions bar
        self._actionsBar.startServerClicked.connect(self._onStartServer)
        self._actionsBar.stopServerClicked.connect(self._onStopServers)
        self._actionsBar.refreshClicked.connect(self._refreshWithValidation)
        self._actionsBar.viewLogsClicked.connect(self._onViewLogs)
        self._actionsBar.autoRefreshToggled.connect(self._onAutoRefreshToggled)
        self._actionsBar.refreshIntervalChanged.connect(self._onRefreshIntervalChanged)

        # Filters bar
        self._filtersBar.filtersChanged.connect(self._applyFilters)

        # List view
        self._listView.startServerRequested.connect(self._onStartServer)
        self._listView.stopServerRequested.connect(self._onStopSelectedServers)
        self._listView.validateServerRequested.connect(self._onValidateServer)
        self._listView.viewLogRequested.connect(self._showServerLog)
        self._listView.serverSelected.connect(self._onServerSelected)
        self._listView.serverDoubleClicked.connect(self._onServerDoubleClicked)

        # Model
        self._model.serverCountChanged.connect(self._actionsBar.setServerCount)
        self._model.beforeRefresh.connect(self._saveSelection)
        self._model.afterRefresh.connect(self._restoreSelectionDelayed)

    def _saveSelection(self):
        """Save current selection before refresh"""
        self._preserved_selection = [s.id for s in self._listView.getSelectedServers()]

    def _restoreSelectionDelayed(self):
        """Restore selection after refresh with a delay"""
        if hasattr(self, '_preserved_selection') and self._preserved_selection:
            QTimer.singleShot(10, lambda: self._restoreSelection(self._preserved_selection))

    def _refreshWithValidation(self):
        """Refresh with validation in background"""
        if self._validation_in_progress:
            return

        # Store current selection before refresh
        self._preserved_selection = [s.id for s in self._listView.getSelectedServers()]

        self._validation_in_progress = True
        self._validation_thread = ValidationThread(self._registry)
        self._validation_thread.validated.connect(self._onValidationComplete)
        self._validation_thread.finished.connect(self._onValidationFinished)
        self._validation_thread.start()

    def _onValidationComplete(self, stopped_count: int):
        """Handle validation completion"""
        if stopped_count > 0:
            # Show a brief notification
            QMessageBox.information(
                self,
                "Servers Validated",
                f"Found {stopped_count} unreachable server(s) and marked as stopped."
            )

        # Refresh the model and restore selection
        self._refreshAndRestoreSelection()

    def _refreshAndRestoreSelection(self):
        """Refresh the model and restore selection"""
        # Get preserved selection or current selection
        selected_ids = getattr(self, '_preserved_selection', None)
        if selected_ids is None:
            selected_ids = [s.id for s in self._listView.getSelectedServers()]

        # Refresh the model
        self._model.refresh()

        # Apply filters again (this might have changed what's visible)
        self._applyFilters()

        # Restore selection after a short delay to ensure view is updated
        if selected_ids:
            QTimer.singleShot(10, lambda: self._restoreSelection(selected_ids))

    def _restoreSelection(self, server_ids: List[str]):
        """Restore selection by server IDs"""
        from PySide6.QtCore import QItemSelectionModel, QModelIndex

        selection_model = self._listView.selectionModel()
        if not selection_model:
            return

        selection_model.clearSelection()

        # Get the actual model being displayed (might be proxy)
        display_model = self._listView.model()

        # Find and select each server
        for server_id in server_ids:
            found = False

            # Search through all rows in the display model
            for row in range(display_model.rowCount()):
                index = display_model.index(row, 0)

                # Get the server data
                server = display_model.data(index, Qt.UserRole)
                if server and server.id == server_id:
                    # Select this row
                    selection_model.select(
                        index,
                        QItemSelectionModel.Select | QItemSelectionModel.Rows
                    )
                    found = True
                    break

            if not found:
                print(f"Server {server_id[:8]} not found in current view (might be filtered)")

        # Clear the preserved selection
        self._preserved_selection = None

    def _onValidationFinished(self):
        """Handle validation thread finish"""
        self._validation_in_progress = False

    def _loadInitialData(self):
        """Load initial server list with validation"""
        # Do initial validation on startup
        self._refreshWithValidation()
        self._applyFilters()

        # Start auto-refresh if enabled
        if self._actionsBar.isAutoRefreshEnabled():
            self._model.setAutoRefresh(True, self._actionsBar.getRefreshInterval())

    def _applyFilters(self):
        """Apply current filters to proxy model"""
        self._filtersBar.applyToProxyModel(self._proxyModel)

    def _onAutoRefreshToggled(self, enabled: bool):
        """Handle auto-refresh toggle"""
        self._model.setAutoRefresh(enabled, self._actionsBar.getRefreshInterval())

    def _onRefreshIntervalChanged(self, interval_ms: int):
        """Handle refresh interval change"""
        if self._actionsBar.isAutoRefreshEnabled():
            self._model.setAutoRefresh(True, interval_ms)

    def _onServerSelected(self, server: ServerRecord):
        """Handle server selection"""
        # Update action bar based on selection
        selected = self._listView.getSelectedServers()
        self._actionsBar.setSelectionCount(len(selected))

    def _onServerDoubleClicked(self, server: ServerRecord):
        """Handle server double-click"""
        if server.state == "running":
            # Open the server URL in default browser
            import webbrowser
            try:
                webbrowser.open(server.base_url)
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Could not open browser",
                    f"Failed to open URL: {server.base_url}\n{e}"
                )
        else:
            # For stopped servers, show the log
            self._showServerLog(server)

    def _onStartServer(self):
        """Handle start server request"""
        dialog = StartServerDialog(self)
        if dialog.exec():
            options = dialog.getOptions()
            self._startServerAsync(options)

    def _startServerAsync(self, options: dict):
        """Start server in background thread"""
        if self._operation_thread and self._operation_thread.isRunning():
            QMessageBox.warning(self, "Operation in Progress",
                                "Another operation is already running.")
            return

        self._operation_thread = ServerOperationThread(
            self._server_manager.start, options
        )
        self._operation_thread.success.connect(self._onServerStarted)
        self._operation_thread.error.connect(self._onServerError)
        self._operation_thread.start()

    def _onServerStarted(self, message: str):
        """Handle successful server start"""
        self._model.refresh()
        QMessageBox.information(self, "Server Started",
                                "ComfyUI server started successfully.")

    def _onServerError(self, error: str):
        """Handle server operation error"""
        QMessageBox.critical(self, "Server Error", f"Operation failed:\n{error}")

    def _onStopServers(self):
        """Handle stop servers from action bar"""
        selected = self._listView.getSelectedServers()
        if selected:
            self._stopServers(selected)

    def _onStopSelectedServers(self, servers: List[ServerRecord]):
        """Handle stop servers from list view"""
        self._stopServers(servers)

    def _stopServers(self, servers: List[ServerRecord]):
        """Stop the given servers"""
        local_host = socket.gethostname()
        local_ips = {"localhost", "127.0.0.1", local_host}

        try:
            local_ips.add(socket.gethostbyname(local_host))
        except Exception:
            pass

        stopped_count = 0
        for server in servers:
            if server.state != "running":
                continue

            # Check if server is local
            if server.host not in local_ips:
                QMessageBox.warning(
                    self,
                    "Remote Server",
                    f"Cannot stop remote server on {server.host}.\n"
                    "Please stop it from the host machine."
                )
                continue

            try:
                success = ComfyServerManager.kill_local_pid(server.pid)
                if success:
                    self._registry.register_stop(server.id)
                    stopped_count += 1
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Stop Failed",
                    f"Failed to stop server {server.id[:8]}:\n{e}"
                )

        if stopped_count > 0:
            self._model.refresh()
            QMessageBox.information(
                self,
                "Servers Stopped",
                f"Successfully stopped {stopped_count} server(s)."
            )

    def _onValidateServer(self, server: ServerRecord):
        """Validate a specific server"""
        is_valid = self._registry.validate_specific(server.id, timeout=2.0)

        if is_valid:
            QMessageBox.information(
                self,
                "Server Valid",
                f"Server {server.id[:8]} is running and reachable."
            )
        else:
            QMessageBox.warning(
                self,
                "Server Unreachable",
                f"Server {server.id[:8]} is not reachable and has been marked as stopped."
            )
            self._model.refresh()

    def _onViewLogs(self):
        """Handle view logs from action bar"""
        selected = self._listView.getSelectedServers()
        if selected:
            self._showServerLog(selected[0])

    def _showServerLog(self, server: ServerRecord):
        """Show server log dialog"""
        if not server.log_path:
            QMessageBox.information(
                self,
                "No Log Available",
                "No log file available for this server."
            )
            return

        dialog = ServerLogDialog(server, self)
        dialog.exec()


def main():
    """Standalone entry point for testing"""
    app = QApplication(sys.argv)

    # Set application style
    app.setStyle("Fusion")

    # Create and show widget
    widget = ServerManagerWidget()
    widget.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()