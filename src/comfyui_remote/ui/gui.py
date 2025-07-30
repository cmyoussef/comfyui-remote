#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Python Prototype UI to help the user to run comfyui workflow
"""

import json
import logging
import os
import re
import sys
import webbrowser
from collections import defaultdict

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5 import uic
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QMessageBox,
    QMainWindow,
    QPushButton,
    QFileDialog,
    QProgressDialog,
    QStatusBar,
)

package_path = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if package_path not in sys.path:
    sys.path.insert(0, package_path)

from comfyui_remote.utils import json_utils, pipe_query
from comfyui_remote.job_runner import ExecuteWorkflow
from comfyui_remote.ui.configs import config

logger = logging.getLogger(__name__)

shows = ["LIBRARY"]
if os.environ["SHOW"] not in shows:
    shows.append(os.environ["SHOW"])


def exception_handler(exc_type, exc_value, exc_traceback):
    """Handle uncaught exceptions by displaying them in a message box."""
    error_message = f"An unexpected error occurred:\n\n{exc_value}"
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Critical)
    msg_box.setWindowTitle("Error")
    msg_box.setText("Application Error")
    msg_box.setInformativeText(error_message)
    msg_box.exec_()


sys.excepthook = exception_handler


class ExecuteWorkflowThread(QThread):
    """Thread to execute workflow in background with interrupt capability."""

    progress = pyqtSignal(int)
    interrupted = pyqtSignal()
    finished = pyqtSignal()

    def __init__(self, run_instance):
        super().__init__()
        self.run_instance = run_instance
        self.run_instance.progress_signal.connect(self.handle_progress)
        self._is_interrupted = False

    def handle_progress(self, value):
        """Handle progress updates from the workflow execution."""
        self.progress.emit(value)

    def run(self):
        """Run the workflow, handling interruptions."""
        try:
            self.run_instance.execute(lambda: self._is_interrupted)
        except Exception:
            pass
        finally:
            if self._is_interrupted:
                self.interrupted.emit()
            else:
                self.finished.emit()

    def stop(self):
        """Request to interrupt execution."""
        self._is_interrupted = True
        self.run_instance.interrupt()


class comfyRemote_UI(QtWidgets.QMainWindow):
    """ComfyUI Remote Windows UI for browsing published templates and launching workflows."""

    def __init__(self, parent=None):
        """Initialize the UI components and connect event handlers."""
        super().__init__(parent)
        uic.loadUi(config.ui_path, self)

        self.selectShow.addItems(shows)

        self.statusBar = QtWidgets.QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready")

        self.setWindowIcon(QtGui.QIcon(config.icon_path))

        self.actionUser_Guide.triggered.connect(self.open_url)
        self.actionTemplate_Guide.triggered.connect(self.open_url)
        self.actionOpen_Custom_Template.triggered.connect(self.open_custom_template)
        self.actionOpen_Local_Folder.triggered.connect(self.open_Local_folder)

        self.templates = []
        self.params = {"int": {}, "float": {}, "str": {}}
        self.json_path = ""

        self.table_view = QtWidgets.QTableView()

        self.model_rootParameters = QtGui.QStandardItemModel()
        self.model_exposedParameters = QtGui.QStandardItemModel()
        self.tableView_ExposedArguments.setModel(self.model_exposedParameters)

        self.connect_UI()

    def open_url(self):
        """Open ComfyUI documentation URLs based on the action menu sender."""
        url = None
        if self.sender().objectName() == "actionUser_Guide":
            url = "http://dnet.dneg.com/display/REDEFINE/comfyui_remote+GUI"
        elif self.sender().objectName() == "actionTemplate_Guide":
            url = "http://dnet.dneg.com/display/REDEFINE/02+-+dntemplates+-+advanced+cases+and+LIBRARY+available"

        if url:
            webbrowser.open(url)

    def populate_data(self, json_path):
        """Load JSON data and populate the exposed parameters table.

        Args:
            json_path: Path to the JSON workflow file.
        """
        json_data = json_utils.load_json_data(json_path)
        self.extract_params(json_data)

        for param_type, param_dict in self.params.items():
            for param_name, default_value in param_dict.items():
                param_item = QtGui.QStandardItem(param_name)
                default_value_item = QtGui.QStandardItem(str(default_value))
                type_item = QtGui.QStandardItem(param_type)

                row = [param_item, default_value_item, type_item]
                self.model_exposedParameters.appendRow(row)

    def open_custom_template(self):
        """Open a file dialog to select and load a custom JSON template."""
        specific_folder = "/user_data/comfyui"

        dialog = QtWidgets.QFileDialog(self, "Select a File")
        dialog.setFileMode(QtWidgets.QFileDialog.ExistingFile)
        dialog.setDirectory(specific_folder)
        dialog.setNameFilters(["JSON Files (*.json)"])
        dialog.setOptions(QtWidgets.QFileDialog.DontUseNativeDialog)
        dialog.setFilter(
            dialog.filter() | QtWidgets.QFileDialog.DontUseCustomDirectoryIcons
        )

        self.clear_template()
        self.clear_data()
        self.fill_rootParameters()

        if dialog.exec_():
            self.json_path = dialog.selectedFiles()[0]
            self.populate_data(self.json_path)
        else:
            self.statusBar.showMessage(
                "select a JSON file exported with API Functionality"
            )

    def open_Local_folder(self):
        """Open the ComfyUI output folder in the file browser."""
        path = "/user_data/comfyui/output"
        if path:
            os.system('xdg-open "%s"' % path)
        else:
            self.statusBar.showMessage("/user_data/ folder not available")

    def clear_template(self):
        """Clear template ComboBox and reset to empty state."""
        self.selectTemplate.clear()
        self.selectTemplate.insertItem(0, "")

    def clear_data(self):
        """Clear model data and parameter dictionaries."""
        self.params = {"int": {}, "float": {}, "str": {}}
        self.model_exposedParameters.removeRows(
            0, self.model_exposedParameters.rowCount()
        )
        self.model_rootParameters.removeRows(0, self.model_rootParameters.rowCount())

    def connect_UI(self):
        """Connect UI signals and set up table headers."""
        self.model_exposedParameters.setHorizontalHeaderLabels(
            ["Parameters", "Values", "hiddenColumn"]
        )
        self.tableView_ExposedArguments.hideColumn(2)

        self.model_rootParameters.setHorizontalHeaderLabels(
            ["Parameters", "Values", "Tooltip"]
        )

        self.selectShow.activated.connect(self.update_show)
        self.selectTemplate.activated.connect(self.update_table)
        self.run.clicked.connect(self.submit_job)

    def update_show(self):
        """Clear UI and query templates for the selected show."""
        self.clear_template()
        self.clear_data()
        self.query_template()

    def update_table(self):
        """Clear data and populate table with selected template."""
        self.clear_data()
        self.fill_rootParameters()
        self.fill_from_template()

    def query_template(self):
        """Load templates from the selected show and populate the template ComboBox.

        Returns:
            List of template dictionaries with name-to-path mappings.
        """
        if self.selectShow.currentText() != "":
            self.selectTemplate.insertItem(0, " ")
            templates_name = []
            templates_name_upscaler = []

            templates = pipe_query.pipequery_send(
                pipe_query.create_find_by_name_tags(
                    show=self.selectShow.currentText(),
                    scopes=[self.selectShow.currentText()],
                    kinds=["ref"],
                    name_tags=[("label", "comfyui_template[^;]*")],
                    task=None,
                )
            )

            for template in templates["data"]["latest_versions"]:
                if template["status"] != "DECLINED":
                    match = re.search(r"_noAPI_", template["name"])
                    if not match:
                        self.templates.append(
                            {template["name"]: template["files"][0]["path"]}
                        )
                        if template["name"].rsplit("_")[6] == "upscale":
                            templates_name_upscaler.append(template["name"])
                        else:
                            templates_name.append(template["name"])

            for template in sorted(templates_name):
                self.selectTemplate.addItem(template)

            for template in sorted(templates_name_upscaler):
                self.selectTemplate.addItem(template)

            self.statusBar.showMessage(
                f"Template Load for {self.selectShow.currentText()}"
            )

            return self.templates

    def extract_params(self, json_data):
        """Extract exposed parameters from JSON workflow data.

        Args:
            json_data: Loaded JSON workflow data.

        Returns:
            Dictionary of parameters categorized by type ('int', 'float', 'str').
        """
        for param_type, search_key in [
            ("int", "dnInteger"),
            ("float", "dnFloat"),
            ("str", "dnString"),
        ]:
            param_list = json_utils.search_params(json_data, search_key)
            for param in param_list:
                default_val = json_utils.display_json_param(json_data, param)
                self.params[param_type][param] = default_val

        return self.params

    def fill_rootParameters(self):
        """Populate the root parameters table with default batch size and frame range."""
        data = [
            ("Batch Size", "1", "The number of times the workflow will run"),
            (
                "Frame Range",
                "N/A",
                "Needs to match input range - Empty or N/A will run all images inside the input directory",
            ),
        ]

        for row, (property_name, value, tooltip) in enumerate(data):
            self.model_rootParameters.setItem(
                row, 0, QtGui.QStandardItem(property_name)
            )
            value_item = QtGui.QStandardItem(str(value))
            self.model_rootParameters.setItem(row, 1, value_item)
            tooltip_item = QtGui.QStandardItem(str(tooltip))
            self.model_rootParameters.setItem(row, 2, tooltip_item)

    def fill_from_template(self):
        """Load and populate data from the selected template."""
        if self.selectTemplate.currentText() != "":
            for template in self.templates:
                if self.selectTemplate.currentText() in template:
                    self.json_path = template[str(self.selectTemplate.currentText())]
                    if self.json_path:
                        self.populate_data(self.json_path)
                    break

    def submit_job(self):
        """Submit the workflow for execution with current parameters."""
        float_args, int_args, str_args = self.get_user_params()
        root_parameters = self.get_root_parameters()
        frame_range = self.get_frame_range(root_parameters)
        batch_size = root_parameters["Batch Size"]

        run = ExecuteWorkflow(
            json_file=self.json_path,
            batch_size=batch_size,
            comfyui_version=None,
            frame_range=frame_range,
            int_args=int_args,
            float_args=float_args,
            str_args=str_args,
        )

        self.progress_dialog = QProgressDialog(
            "Running in terminal, please wait...", None, 0, 0, self
        )
        self.progress_dialog.setWindowTitle("Executing")
        self.progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
        self.progress_dialog.setCancelButtonText("Interrupt")
        self.progress_dialog.canceled.connect(self.interrupt_execution)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setRange(0, 100)

        self.thread = ExecuteWorkflowThread(run)

        self.thread.progress.connect(self.progress_dialog.setValue)
        self.thread.finished.connect(self.progress_dialog.close)
        self.thread.interrupted.connect(self.progress_dialog.close)
        self.thread.finished.connect(self.execution_complete)

        self.progress_dialog.show()
        self.thread.start()

    def get_user_params(self):
        """Extract user parameters from the exposed parameters table.

        Returns:
            Tuple of (float_args, int_args, str_args) as JSON strings or None.
        """
        exposedParameters = {"int": {}, "float": {}, "str": {}, "other": {}}
        for row in range(self.model_exposedParameters.rowCount()):
            key = self.model_exposedParameters.index(row, 0).data()
            value = self.model_exposedParameters.index(row, 1).data()
            hidden_data = self.model_exposedParameters.index(row, 2).data()

            if hidden_data == "int":
                exposedParameters["int"][key] = int(value)
            elif hidden_data == "float":
                exposedParameters["float"][key] = float(value)
            elif hidden_data == "str":
                exposedParameters["str"][key] = str(value)

        int_args = (
            json.dumps(exposedParameters["int"]) if exposedParameters["int"] else None
        )
        float_args = (
            json.dumps(exposedParameters["float"])
            if exposedParameters["float"]
            else None
        )
        str_args = (
            json.dumps(exposedParameters["str"]) if exposedParameters["str"] else None
        )

        return float_args, int_args, str_args

    def get_root_parameters(self):
        """Extract root parameters from the root parameters table.

        Returns:
            Dictionary of root parameter key-value pairs.
        """
        rootParameters = defaultdict()
        for row in range(self.model_rootParameters.rowCount()):
            key = self.model_rootParameters.item(row, 0).text()
            value = self.model_rootParameters.item(row, 1).text()
            rootParameters[key] = value
        return rootParameters

    def get_frame_range(self, rootParameters):
        """Extract and validate frame range from root parameters.

        Args:
            rootParameters: Dictionary of root parameters.

        Returns:
            Frame range string or None if invalid/empty.
        """
        frame_range = rootParameters["Frame Range"]
        invalid_values = ["", "0", "0-0", "N/A", "n/a"]
        if not frame_range or frame_range in invalid_values:
            frame_range = None
        return frame_range

    def execution_complete(self):
        """Handle completion of the execution."""
        self.progress_dialog.close()
        QMessageBox.information(
            self,
            "Execution Complete",
            "The workflow execution has finished successfully.",
        )

    def interrupt_execution(self):
        """Handle user interrupt request."""
        if self.thread.isRunning():
            self.thread.stop()  # Custom method in thread to handle stopping
        self.progress_dialog.close()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    mainWindow = comfyRemote_UI()
    mainWindow.show()
    sys.exit(app.exec_())
