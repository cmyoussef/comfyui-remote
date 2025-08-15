"""Main window."""
from PyQt5 import QtWidgets
from .viewmodels.workflow_viewmodel import WorkflowViewModel
from .viewmodels.parameters_model import ParametersModel
from .viewmodels.runs_model import RunsModel
from .controllers.run_controller import RunController
from ..theme.theme_manager import ThemeManager


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ComfyUI Remote")
        self.resize(900, 640)
        self._init_ui()

    def _init_ui(self):
        ThemeManager().apply(self)
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)

        self._wf_vm = WorkflowViewModel()
        self._params_model = ParametersModel()
        self._runs_model = RunsModel()
        self._controller = RunController(self._wf_vm, self._params_model, self._runs_model)

        top = QtWidgets.QHBoxLayout()
        self._workflow_edit = QtWidgets.QLineEdit()
        self._browse_btn = QtWidgets.QPushButton("Browse Workflow…")
        self._run_btn = QtWidgets.QPushButton("Run")
        top.addWidget(self._workflow_edit)
        top.addWidget(self._browse_btn)
        top.addWidget(self._run_btn)

        self._table = QtWidgets.QTableView()
        self._table.setModel(self._params_model)

        layout.addLayout(top)
        layout.addWidget(self._table)

        self.setCentralWidget(central)

        self._browse_btn.clicked.connect(self._on_browse)
        self._run_btn.clicked.connect(self._on_run)

    def _on_browse(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Workflow JSON", "", "JSON (*.json)")
        if fn:
            self._workflow_edit.setText(fn)
            self._controller.load_workflow_file(fn)

    def _on_run(self):
        self._controller.run_local()
