# src/comfyui_remote/ui/server_manager/models/server_list_model.py
from __future__ import annotations

from typing import List, Any, Optional, Dict
from datetime import datetime
from enum import IntEnum
from PySide6.QtCore import (
    QAbstractTableModel, Qt, QModelIndex, Signal, QTimer,
    QSortFilterProxyModel
)
from PySide6.QtGui import QColor, QIcon, QFont

from ....connectors.comfy.server_registry import ServerRegistry, ServerRecord


class ServerColumns(IntEnum):
    """Column indices for the server list table"""
    STATUS = 0
    ID = 1
    HOST = 2
    PORT = 3
    PID = 4
    OWNER = 5
    STARTED = 6
    TAGS = 7
    URL = 8

    @classmethod
    def count(cls) -> int:
        return len(cls)

    @classmethod
    def headers(cls) -> List[str]:
        return [
            "Status", "ID", "Host", "Port", "PID",
            "Owner", "Started", "Tags", "URL"
        ]


class ServerListModel(QAbstractTableModel):
    """Model for displaying ComfyUI servers from the registry"""

    # Signals
    serverUpdated = Signal(ServerRecord)
    serverCountChanged = Signal(int)

    def __init__(self, registry: Optional[ServerRegistry] = None, parent=None):
        super().__init__(parent)
        self._registry = registry or ServerRegistry()
        self._servers: List[ServerRecord] = []
        self._column_count = ServerColumns.count()

        # Auto-refresh timer
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._autoRefresh)
        self._refresh_timer.setInterval(5000)  # 5 seconds

        # Initial load
        self.refresh()

    def _autoRefresh(self):
        """Auto refresh that signals the need to preserve selection"""
        self.beforeRefresh.emit()  # Signal to save selection
        self.refresh()
        self.afterRefresh.emit()  # Signal to restore selection

    # Add these signals at the class level (after the existing signals)
    beforeRefresh = Signal()
    afterRefresh = Signal()

    def setAutoRefresh(self, enabled: bool, interval_ms: int = 5000):
        """Enable/disable auto-refresh"""
        if enabled:
            self._refresh_timer.setInterval(interval_ms)
            self._refresh_timer.start()
        else:
            self._refresh_timer.stop()

    def refresh(self):
        """Reload servers from registry with validation"""
        self.beginResetModel()
        try:
            # First validate and clean up stale entries
            self._registry.validate_and_update(timeout=1.0)

            # Now get the updated list
            self._servers = self._registry.list_latest()
            # No need to sort here - the view handles sorting
        except Exception as e:
            print(f"Error refreshing server list: {e}")
            self._servers = []
        self.endResetModel()
        self.serverCountChanged.emit(len(self._servers))

    def getServer(self, row: int) -> Optional[ServerRecord]:
        """Get server record at given row"""
        if 0 <= row < len(self._servers):
            return self._servers[row]
        return None

    def getServerById(self, server_id: str) -> Optional[ServerRecord]:
        """Find server by ID"""
        for server in self._servers:
            if server.id == server_id:
                return server
        return None

    # --- QAbstractTableModel interface ---

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._servers)

    def columnCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return self._column_count

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()

        if row >= len(self._servers):
            return None

        server = self._servers[row]

        if role == Qt.DisplayRole:
            return self._getDisplayData(server, col)
        elif role == Qt.DecorationRole:
            return self._getDecorationData(server, col)
        elif role == Qt.ForegroundRole:
            return self._getForegroundData(server, col)
        elif role == Qt.FontRole:
            return self._getFontData(server, col)
        elif role == Qt.ToolTipRole:
            return self._getToolTipData(server, col)
        elif role == Qt.UserRole:
            # Return the full server record for custom use
            return server
        elif role == Qt.UserRole + 1:  # Custom sort role
            return self._getSortData(server, col)

        return None

    def _getSortData(self, server: ServerRecord, col: int) -> Any:
        """Return data for sorting"""
        if col == ServerColumns.STATUS:
            # Sort running before stopped
            return 0 if server.state == "running" else 1
        elif col == ServerColumns.STARTED:
            # Sort by actual timestamp, not display string
            return server.started_at or ""
        elif col == ServerColumns.PORT:
            return server.port
        elif col == ServerColumns.PID:
            return server.pid
        else:
            # For other columns, use display data
            return self._getDisplayData(server, col)

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.DisplayRole) -> Any:
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            headers = ServerColumns.headers()
            if 0 <= section < len(headers):
                return headers[section]
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    # --- Data formatting helpers ---

    def _getDisplayData(self, server: ServerRecord, col: int) -> str:
        if col == ServerColumns.STATUS:
            return server.state.capitalize()
        elif col == ServerColumns.ID:
            return server.id[:8]  # Show first 8 chars
        elif col == ServerColumns.HOST:
            return server.host
        elif col == ServerColumns.PORT:
            return str(server.port)
        elif col == ServerColumns.PID:
            return str(server.pid)
        elif col == ServerColumns.OWNER:
            return f"{server.owner_user}@{server.owner_host}"
        elif col == ServerColumns.STARTED:
            return self._formatTimestamp(server.started_at)
        elif col == ServerColumns.TAGS:
            return ", ".join(server.tags or [])
        elif col == ServerColumns.URL:
            return server.base_url
        return ""

    def _getDecorationData(self, server: ServerRecord, col: int) -> Optional[QIcon]:
        if col == ServerColumns.STATUS:
            # Return status icon (implement icon loading in common/icons.py)
            # For now, return None
            pass
        return None

    def _getForegroundData(self, server: ServerRecord, col: int) -> Optional[QColor]:
        if col == ServerColumns.STATUS:
            if server.state == "running":
                return QColor(0, 200, 0)  # Green
            elif server.state == "stopped":
                return QColor(200, 0, 0)  # Red
        return None

    def _getFontData(self, server: ServerRecord, col: int) -> Optional[QFont]:
        if col == ServerColumns.STATUS:
            font = QFont()
            font.setBold(True)
            return font
        return None

    def _getToolTipData(self, server: ServerRecord, col: int) -> str:
        if col == ServerColumns.ID:
            return server.id  # Show full ID in tooltip
        elif col == ServerColumns.STARTED:
            return f"Started: {server.started_at}\nStopped: {server.stopped_at or 'N/A'}"
        elif col == ServerColumns.URL:
            return f"Click to copy: {server.base_url}"
        return ""

    def _formatTimestamp(self, iso_str: Optional[str]) -> str:
        """Format ISO timestamp for display"""
        if not iso_str:
            return ""
        try:
            # Parse the ISO string
            from datetime import datetime, timezone

            # Handle both Z suffix and +00:00 format
            if iso_str.endswith('Z'):
                dt = datetime.fromisoformat(iso_str[:-1] + '+00:00')
            else:
                dt = datetime.fromisoformat(iso_str)

            # Get current time in UTC
            now = datetime.now(timezone.utc)

            # Calculate the time difference
            delta = now - dt

            # Convert to seconds for accurate calculation
            total_seconds = delta.total_seconds()

            if total_seconds < 0:
                return "Future"
            elif total_seconds < 60:
                return "Just now"
            elif total_seconds < 3600:  # Less than 1 hour
                minutes = int(total_seconds / 60)
                return f"{minutes}m ago"
            elif total_seconds < 86400:  # Less than 1 day
                hours = int(total_seconds / 3600)
                return f"{hours}h ago"
            elif total_seconds < 604800:  # Less than 1 week
                days = int(total_seconds / 86400)
                return f"{days}d ago"
            else:
                weeks = int(total_seconds / 604800)
                return f"{weeks}w ago"

        except Exception as e:
            print(f"Error formatting timestamp {iso_str}: {e}")
            # Fallback to showing date part only
            return iso_str[:19] if len(iso_str) >= 19 else iso_str


class ServerFilterProxyModel(QSortFilterProxyModel):
    """Proxy model for filtering servers"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._show_running = True
        self._show_stopped = False
        self._tag_filter: List[str] = []
        self._host_filter = ""

        # Use custom sort role for proper sorting
        self.setSortRole(Qt.UserRole + 1)

    def setShowRunning(self, show: bool):
        self._show_running = show
        self.invalidateFilter()

    def setShowStopped(self, show: bool):
        self._show_stopped = show
        self.invalidateFilter()

    def setTagFilter(self, tags: List[str]):
        self._tag_filter = tags
        self.invalidateFilter()

    def setHostFilter(self, host: str):
        self._host_filter = host.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if not model:
            return False

        # Get the server record
        index = model.index(source_row, 0, source_parent)
        server = model.data(index, Qt.UserRole)

        if not server:
            return False

        # Filter by state
        if server.state == "running" and not self._show_running:
            return False
        if server.state == "stopped" and not self._show_stopped:
            return False

        # Filter by tags
        if self._tag_filter:
            server_tags = set(server.tags or [])
            if not any(tag in server_tags for tag in self._tag_filter):
                return False

        # Filter by host
        if self._host_filter:
            if self._host_filter not in server.host.lower():
                return False

        return True