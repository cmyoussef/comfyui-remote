import os

### Base Remote_GUI dir
basedir = os.path.dirname(os.path.dirname(__file__))

# Path to remote GUI UI
ui_path = os.path.join(os.path.join(basedir, "ui"), "remoteUI_v001.ui")

# Path to remote GUI stylesheet
stylesheet_path = os.path.join(os.path.join(basedir, "ui"), "styleSheet01.qss")

# Path to remote GUI icon
icon_path = os.path.join(os.path.join(basedir, "icon"), "remoteUI_icon.png")
