# src/comfyui_remote/ui/server_manager/views/server_list_view.py
from __future__ import annotations

from typing import Optional, List
from PySide6.QtWidgets import (
    QTableView, QHeaderView, QMenu, QMessageBox,
    QApplication
)
from PySide6.QtCore import Qt, Signal, QModelIndex, QPoint
from PySide6.QtGui import QAction, QKeySequence, QClipboard

from ....connectors.comfy.server_registry import ServerRecord


class ServerListView(QTableView):
    """Custom table view for displaying servers"""

    # Signals
    serverSelected = Signal(ServerRecord)  # Emitted when a server is selected
    serverDoubleClicked = Signal(ServerRecord)  # Emitted on double-click
    startServerRequested = Signal()  # Request to start new server
    stopServerRequested = Signal(list)  # Request to stop server(s)
    validateServerRequested = Signal(ServerRecord)  # Request to validate server
    viewLogRequested = Signal(ServerRecord)  # Request to view server log
    copyUrlRequested = Signal(str)  # Request to copy URL

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setupView()
        self._createActions()

    def _setupView(self):
        """Configure the table view"""
        # Selection behavior
        self.setSelectionBehavior(QTableView.SelectRows)
        self.setSelectionMode(QTableView.ExtendedSelection)

        # Appearance
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.setShowGrid(False)

        # Header configuration
        header = self.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.Interactive)

        # Context menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._showContextMenu)

        # Signals
        self.doubleClicked.connect(self._onDoubleClick)

    def _createActions(self):
        """Create context menu actions"""
        self._startAction = QAction("Start New Server", self)
        self._startAction.setShortcut(QKeySequence("Ctrl+N"))
        self._startAction.triggered.connect(self.startServerRequested.emit)

        self._stopAction = QAction("Stop Server(s)", self)
        self._stopAction.setShortcut(QKeySequence("Delete"))
        self._stopAction.triggered.connect(self._onStopServers)

        self._validateAction = QAction("Validate Server", self)
        self._validateAction.setShortcut(QKeySequence("Ctrl+V"))
        self._validateAction.triggered.connect(self._onValidateServer)

        self._viewLogAction = QAction("View Log", self)
        self._viewLogAction.setShortcut(QKeySequence("Ctrl+L"))
        self._viewLogAction.triggered.connect(self._onViewLog)

        self._copyUrlAction = QAction("Copy URL", self)
        self._copyUrlAction.setShortcut(QKeySequence("Ctrl+C"))
        self._copyUrlAction.triggered.connect(self._onCopyUrl)

        self._refreshAction = QAction("Refresh", self)
        self._refreshAction.setShortcut(QKeySequence("F5"))
        self._refreshAction.triggered.connect(self._onRefresh)

        # Add actions to view for shortcuts to work
        self.addAction(self._startAction)
        self.addAction(self._stopAction)
        self.addAction(self._validateAction)
        self.addAction(self._viewLogAction)
        self.addAction(self._copyUrlAction)
        self.addAction(self._refreshAction)

    def _showContextMenu(self, pos: QPoint):
        """Show context menu at position"""
        index = self.indexAt(pos)
        menu = QMenu(self)

        menu.addAction(self._startAction)
        menu.addSeparator()

        if index.isValid():
            server = self._getServerFromIndex(index)
            if server:
                if server.state == "running":
                    menu.addAction(self._stopAction)
                    menu.addAction(self._validateAction)
                menu.addAction(self._viewLogAction)
                menu.addAction(self._copyUrlAction)
                menu.addSeparator()

        menu.addAction(self._refreshAction)

        menu.exec_(self.mapToGlobal(pos))

    def _getServerFromIndex(self, index: QModelIndex) -> Optional[ServerRecord]:
        """Get server record from model index"""
        if not index.isValid():
            return None

        # Handle proxy model
        model = self.model()
        if hasattr(model, 'sourceModel'):
            source_index = model.mapToSource(index)
            source_model = model.sourceModel()
            return source_model.data(source_index, Qt.UserRole)
        else:
            return model.data(index, Qt.UserRole)

    def getSelectedServers(self) -> List[ServerRecord]:
        """Get all selected servers"""
        servers = []
        for index in self.selectionModel().selectedRows():
            server = self._getServerFromIndex(index)
            if server:
                servers.append(server)
        return servers

    def _onDoubleClick(self, index: QModelIndex):
        """Handle double-click on server"""
        server = self._getServerFromIndex(index)
        if server:
            self.serverDoubleClicked.emit(server)

    def _onStopServers(self):
        """Handle stop server action"""
        servers = self.getSelectedServers()
        running_servers = [s for s in servers if s.state == "running"]

        if not running_servers:
            QMessageBox.information(
                self,
                "No Running Servers",
                "Please select running servers to stop."
            )
            return

        # Confirm action
        count = len(running_servers)
        msg = f"Stop {count} server{'s' if count > 1 else ''}?"
        reply = QMessageBox.question(
            self,
            "Confirm Stop",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.stopServerRequested.emit(running_servers)

    def _onValidateServer(self):
        """Handle validate server action"""
        servers = self.getSelectedServers()
        if servers and servers[0].state == "running":
            self.validateServerRequested.emit(servers[0])

    def _onViewLog(self):
        """Handle view log action"""
        servers = self.getSelectedServers()
        if servers:
            self.viewLogRequested.emit(servers[0])

    def _onCopyUrl(self):
        """Handle copy URL action"""
        servers = self.getSelectedServers()
        if servers:
            url = servers[0].base_url
            clipboard = QApplication.clipboard()
            clipboard.setText(url)
            self.copyUrlRequested.emit(url)

    def _onRefresh(self):
        """Handle refresh action with selection preservation"""
        # Store current selection
        selected_ids = [s.id for s in self.getSelectedServers()]

        # Get the model and refresh
        model = self.model()
        if hasattr(model, 'sourceModel'):
            source_model = model.sourceModel()
        else:
            source_model = model

        if hasattr(source_model, 'refresh'):
            source_model.refresh()

        # Restore selection after a short delay
        if selected_ids:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(10, lambda: self._restoreSelection(selected_ids))

    def _restoreSelection(self, server_ids: list):
        """Restore selection by server IDs"""
        from PySide6.QtCore import QItemSelectionModel, Qt

        selection_model = self.selectionModel()
        if not selection_model:
            return

        selection_model.clearSelection()

        model = self.model()

        # Find and select each server
        for server_id in server_ids:
            for row in range(model.rowCount()):
                index = model.index(row, 0)
                server = model.data(index, Qt.UserRole)

                if server and server.id == server_id:
                    # Select this row
                    selection_model.select(
                        index,
                        QItemSelectionModel.Select | QItemSelectionModel.Rows
                    )
                    break

    def selectionChanged(self, selected, deselected):
        """Override to emit signal when selection changes"""
        super().selectionChanged(selected, deselected)

        servers = self.getSelectedServers()
        if servers:
            self.serverSelected.emit(servers[0])

    def resizeColumnsToContents(self):
        """Resize columns to fit content"""
        for i in range(self.model().columnCount()):
            self.resizeColumnToContents(i)