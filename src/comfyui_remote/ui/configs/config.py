import os

### Base GUI dir
basedir = os.path.dirname(os.path.dirname(__file__))

# Path to remote GUI UI
ui_path = os.path.join(os.path.join(basedir, "resources"), "comfyui_remote.ui")

# Path to remote GUI stylesheet
stylesheet_path = os.path.join(os.path.join(basedir, "resources"), "comfyui_remote.qss")

# Path to remote GUI icon
icon_path = os.path.join(os.path.join(basedir, "resources"), "comfyui_remote_icon.png")
