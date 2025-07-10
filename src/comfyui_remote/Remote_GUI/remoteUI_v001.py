#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Python Prototype UI to help the user to run comfyui template
"""

# Import general Library:
import sys
import os
from collections import defaultdict
import json
import subprocess
import threading
from tqdm import tqdm
import time

# Get the absolute path of the package.
package_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# This is done by inserting the local package path at the beginning of sys.path, which gives it precedence over installed packages.
if package_path not in sys.path:
    sys.path.insert(0, package_path)
    
# Available in dnegPipe5
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QProgressDialog
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication, QMessageBox, QMainWindow, QPushButton
from PyQt5 import uic

from ComfyUI_remote.utils import json_utils
from ComfyUI_remote.utils import pipe_query 
from ComfyUI_remote.executors.api_executor import ComfyConnector
from ComfyUI_remote.launcher import ExecuteWorkflow
from ComfyUI_remote.utils.common_utils import display_command
from ComfyUI_remote.Remote_GUI.configs import config

import webbrowser


__author__ = "Romain Bouvard"
__email__ = "rnb@dneg.com"
__version__ = "0.1.01"
__date__ = "November 2024"
__status__ = "Dev"

# Set Primary SHOW location:
shows = ['LIBRARY']

# and Avoid LIBRARY to be duplicated in list of Shows if set as dnshow:
if os.environ['SHOW'] not in shows:
    shows.append(os.environ['SHOW'])

# Custom exception handler
def exception_handler(exc_type, exc_value, exc_traceback):
    error_message = f"An unexpected error occurred:\n\n{exc_value}"
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Critical)
    msg_box.setWindowTitle("Error")
    msg_box.setText("Application Error")
    msg_box.setInformativeText(error_message)
    msg_box.exec_()

# Set the custom handler
sys.excepthook = exception_handler

class ExecuteWorkflowThread(QThread):
    """Thread to execute workflow."""
    progress = pyqtSignal(int)  # Signal to communicate progress updates
    finished = pyqtSignal()  # Signal when execution is complete

    def __init__(self, run_instance):
        super().__init__()
        self.run_instance = run_instance

    def run(self):
        # Simulate execution process with a loading bar
        for i in range(100):
            time.sleep(0.05)  # Simulate work being done
            self.progress.emit(i + 1)  # Emit progress
        self.run_instance.execute()
        self.finished.emit()  # Notify that execution is finished

class comfyRemote_UI(QtWidgets.QMainWindow):
    """ ComfyUI Remote Windows UI for Browsing published Templates and launch on local  """

    def __init__ (self, parent=None):
        
        """ 
        setup Init file and load .ui file, qss and icon
         - StatusBar
        """
        super().__init__(parent)
        uic.loadUi(config.ui_path, self)

        # set UI Shows
        self.selectShow.addItems(shows)

        # StyleSheet and QSS File:
        stylesheet_file = QtCore.QFile(config.stylesheet_path)
        stylesheet_file.open(QtCore.QFile.ReadOnly)
        stylesheet = QtCore.QTextStream(stylesheet_file)
        self.setStyleSheet(stylesheet.readAll())
 
        #StatusBar from QMainWindow:
        self.statusBar = QtWidgets.QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage('Ready')

        # icons:
        self.setWindowIcon(QtGui.QIcon(config.icon_path))

        # Action Menu:
        self.actionUser_Guide.triggered.connect(self.open_url)
        self.actionTemplate_Guide.triggered.connect(self.open_url)
        self.actionOpen_Custom_Template.triggered.connect(self.open_custom_template)
        self.actionOpen_Local_Folder.triggered.connect(self.open_Local_folder)

        # variables:
        self.templates = []
        self.params = {'int': {}, 'float': {}, 'str': {}}
        self.json_path = ''

        # Create the two table view and set the data models
        self.table_view = QtWidgets.QTableView()
        
        # Root Parameters:
        self.model_rootParameters = QtGui.QStandardItemModel()
        self.tableView_RootParameters.setModel(self.model_rootParameters)

        # Exposed Parameters:
        self.model_exposedParameters = QtGui.QStandardItemModel()
        self.tableView_ExposedArguments.setModel(self.model_exposedParameters)

        # Populate:
        self.connect_UI()

    def open_url(self):
        '''
        Function to open specific URL of COMFYUI in DNET. URL currently hardcoded from actionMenu sender
        '''
        if self.sender().objectName() == 'actionUser_Guide':
            url = "http://dnet.dneg.com/display/REDEFINE/comfyui_remote+GUI"

        if self.sender().objectName() == 'actionTemplate_Guide':
            url = "http://dnet.dneg.com/display/REDEFINE/02+-+dntemplates+-+advanced+cases+and+LIBRARY+available"
            
        webbrowser.open(url)

    def open_custom_template(self):
        '''
        Function to build for Opening a Non Publish Template
        Useful for User to test before publishing
        '''
        pass

    def open_Local_folder(self):
        """
        Opening File System Browser to /user_data/output/ folder
        """
        path = "/user_data/comfyui/output"
        if path:
            os.system('xdg-open "%s"' % path)
        else: 
            self.statusBar.showMessage('/user_data/ folder not available')

    def clear_template(self):
        ''' Clear All Data from show update'''
        # Clear Template ComboBox:
        self.selectTemplate.clear()
        self.selectTemplate.insertItem(0,"")

    def clear_data(self):
        # Clear Model data and dictionnary:
        self.params = {'int': {}, 'float': {}, 'str': {}}
        self.model_exposedParameters.removeRows(0, self.model_exposedParameters.rowCount())
        self.model_rootParameters.removeRows(0, self.model_rootParameters.rowCount())

    def connect_UI(self):
        """
        Connector function to pass arguments
        """
        # Set the headers as numbers
        self.model_exposedParameters.setHorizontalHeaderLabels(["Parameters", "Values", "hiddenColumn"])
        self.tableView_ExposedArguments.hideColumn(2)

        # Set the headers as numbers
        self.model_rootParameters.setHorizontalHeaderLabels(["Parameters", "Values", "Tooltip"])

        self.selectShow.activated.connect(self.update_show)
        self.selectTemplate.activated.connect(self.update_table)
        self.run.clicked.connect(self.export_table)

    def update_show(self):
        """
        Start with a clean slate of Template list / UI ComboBox and TableView:
        """
        self.clear_template()
        self.clear_data()
        self.query_template()

    def update_table(self):
        """Start with clean table """
        self.clear_data()
        self.fill_rootParameters()
        self.fill_from_template()
    
    def query_template(self):
        """
        Load Templates from SHOW selected - Default is LIBRARY
            Return: list of Stalks - Spider Query
        """

        if self.selectShow.currentText()!= '':

            # Start the ComboBox with an Empty Entry
            self.selectTemplate.insertItem(0," ")
            templates_name = []
            templates_name_upscaler = []

            templates = pipe_query.pipequery_send(pipe_query.create_find_by_name_tags(
                show = self.selectShow.currentText(),
                scopes=[self.selectShow.currentText()],
                kinds=["ref"],
                name_tags=[("label", "comfyui_template[^;]*")],
                task=None
            ))

            # get {names:filePath} as a LIST in self.templates for Status different of DECLINED:
            for template in templates['data']['latest_versions']:
                if template['status'] != 'DECLINED':
                    self.templates.append({template['name']:template['files'][0]['path']})
                    if template['name'].rsplit('_')[6] == 'upscale':
                        templates_name_upscaler.append(template['name'])
                    else:
                        templates_name.append(template['name'])

            #Populate comboBox
            for template in sorted(templates_name):
                self.selectTemplate.addItem(template)

            for template in sorted(templates_name_upscaler):
                self.selectTemplate.addItem(template)
            
            # Show message and return all templates stalkname into list:
            self.statusBar.showMessage(f"Template Load for {self.selectShow.currentText()}")

            return self.templates

    def extract_params(self, json_data):
        """
        Collect exposed arguments and their default values from a JSON file.
        
        Args:
            json_data: Loaded JSON data.
        
        Returns:
            A dictionary of parameters and their default values, categorized by type ('int', 'float', 'str').
        """

        # Process each parameter type
        for param_type, search_key in [('int', 'dnInteger'), ('float', 'dnFloat'), ('str', 'dnString')]:
            # Search for parameters of the current type
            param_list = json_utils.search_params(json_data, search_key)
            for param in param_list:
                # Get the default value for each parameter
                default_val = json_utils.display_json_param(json_data, param)
                # Add the parameter and its default value to the dictionary
                self.params[param_type][param] = default_val

        return self.params

    def fill_rootParameters(self):
        """
        Fill Basic tableView for the root parameters with:
         - Batch size default at 1
         - Frame Range default to N/A
        """
        
        data = [
            ('Batch Size', '1', 'The number of times the template will run'),
            ('Frame Range', 'N/A', 'Needs to match input range - Empty or N/A will run all images inside the input directory'),
        ]
        
        # Populate the table
        for row, (property_name, value, tooltip) in enumerate(data):
            self.model_rootParameters.setItem(row, 0, QtGui.QStandardItem(property_name))  # Property name
            value_item = QtGui.QStandardItem(str(value))
            self.model_rootParameters.setItem(row, 1, value_item)
            tooltip_item = QtGui.QStandardItem(str(tooltip))
            self.model_rootParameters.setItem(row, 2, tooltip_item)

    def fill_from_template(self):
        """
        Fill the tableView using the json_file, normalizing data to fit TableView requirement:
        """

        if self.selectTemplate.currentText() != '':
            # get and load json data
            for template in self.templates:
                if self.selectTemplate.currentText() in template:
                    self.json_path = template[str(self.selectTemplate.currentText())]
                    
                    if self.json_path:
                        json_data = json_utils.load_json_data(self.json_path)
                        self.extract_params(json_data)
            
                        for param_type, param_dict in self.params.items():
                            for param_name, default_value in param_dict.items():
                                # Create items for the row
                                param_item = QtGui.QStandardItem(param_name)
                                default_value_item = QtGui.QStandardItem(str(default_value))
                                type_item = QtGui.QStandardItem(param_type)

                                row = [param_item, default_value_item, type_item]
                                self.model_exposedParameters.appendRow(row)
                    break

    def export_table(self):
        """
        Function to export the current tableView data to dictionnary matching previous data.
        Return: dictionnary key/values as exposed_parameters/users_inputs
        """
        # Currently not matching the self.params dictionnary formatting. 
        # Need to include Float (or empty parameters as they are ditch from the self.params)
        
        # Export Exposed Parameters:
        '''
        exposedParameters = {"int": [], "float": [], "str": [], "other": {}}
        for row in range(self.model_exposedParameters.rowCount()):
            key = self.model_exposedParameters.item(row, 2).text()  # Access the hidden column
            name = self.model_exposedParameters.item(row, 0).text()  # Access 'Name' (column 0)
            value = self.model_exposedParameters.item(row, 1).text()  # Access 'Value' (column 1)
            exposedParameters[key]={name: value}  # Group as dicts
        '''
        exposedParameters = {"int": {}, "float": {}, "str": {}, "other": {}}

        for row in range(self.model_exposedParameters.rowCount()):
            key = self.model_exposedParameters.index(row, 0).data()  # Get data from column 0 (key)
            value = self.model_exposedParameters.index(row, 1).data()  # Get data from column 1 (value)
            hidden_data = self.model_exposedParameters.index(row, 2).data()  # Get data from the hidden column (data type)
            
            if hidden_data == 'int':
                exposedParameters['int'][key] = int(value)

            elif hidden_data == 'float':
                exposedParameters['float'][key] = float(value)

            elif hidden_data == 'str':
                exposedParameters['str'][key] = str(value)

        
        # Export Roots Parameters:
        rootParameters = defaultdict()
        for row in range(self.model_rootParameters.rowCount()):
            key = self.model_rootParameters.item(row, 0).text()
            value = self.model_rootParameters.item(row, 1).text()
            rootParameters[key] = value


        # Define args if any and convert to JSON string, else None.
        if exposedParameters["int"]:
            int_args=exposedParameters["int"]
            int_args = json.dumps(int_args)
        else:
            int_args=None
        
        if exposedParameters['float']:
            float_args=exposedParameters['float']
            float_args = json.dumps(float_args)
        else:
            float_args=None

        if exposedParameters['str']:
            str_args=exposedParameters['str']
            str_args = json.dumps(str_args)
        else:
            str_args=None
    
        frame_range = rootParameters['Frame Range']
        if not frame_range or frame_range=='0' or frame_range=='0-0' or frame_range=='N/A' or frame_range=='n/a':
            frame_range = None

        batch_size = rootParameters['Batch Size']

        run = ExecuteWorkflow(
            json_file = self.json_path, 
            batch_size= batch_size,
            frame_range= frame_range,
            int_args=int_args,
            float_args=float_args,
            str_args=str_args,
            remote_gui=True
            )

        # Start the threaded execution with an indeterminate progress dialog
        self.progress_dialog = QProgressDialog("Running in terminal, please wait...", None, 0, 0, self)
        self.progress_dialog.setWindowTitle("Executing")
        self.progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
        self.progress_dialog.setCancelButton(None)  # Remove the cancel button
        self.progress_dialog.setMinimumDuration(0)  # Show immediately
        self.progress_dialog.setRange(0, 0)  # Indeterminate mode
        self.progress_dialog.show()

        self.thread = ExecuteWorkflowThread(run)
        
        #self.statusBar.showMessage(command_summary)
        self.thread.finished.connect(self.execution_complete)
        self.thread.start()

    def execution_complete(self):
        """Handle completion of the execution."""
        self.progress_dialog.close()
        QMessageBox.information(self, "Execution Complete", "The workflow execution has finished successfully.")


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    mainWindow = comfyRemote_UI()
    mainWindow.show()
    sys.exit(app.exec_())