"""VM: parameters table."""
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt, QAbstractTableModel, QModelIndex
from typing import List, Tuple, Any
from ....nodes.core.graph import Graph


class ParametersModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._rows: List[Tuple[str, str, Any]] = []

    def set_graph(self, g: Graph) -> None:
        self.beginResetModel()
        self._rows.clear()
        for n in g.iter_nodes():
            for k, v in n.params().items():
                self._rows.append((n.meta().label or n.meta().type, k, v))
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 3

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid(): return None
        if role in (Qt.DisplayRole, Qt.EditRole):
            return self._rows[index.row()][index.column()]
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole: return None
        if orientation == Qt.Horizontal:
            return ["Node", "Param", "Value"][section]
        return section + 1

    def flags(self, index):
        if not index.isValid(): return Qt.ItemIsEnabled
        if index.column() == 2:
            return Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or not index.isValid(): return False
        node, key, _ = self._rows[index.row()]
        self._rows[index.row()] = (node, key, value)
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        return True
