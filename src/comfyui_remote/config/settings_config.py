import os
import inspect
import uuid
import json

home_directory = os.path.expanduser("~")
username = os.path.basename(home_directory)

current_dir = os.path.dirname(
    os.path.abspath(inspect.getfile(inspect.currentframe()))
)  # .../ComfyUI-to-Python-Extension-dev/config
DIR_PATH = os.path.dirname(current_dir)  # .../ComfyUI-to-Python-Extension-dev

local_comfy_path = "/user_data/comfyui/"
local_comfy_outputs = os.path.join(local_comfy_path, "output")
local_comfy_input = os.path.join(local_comfy_path, "input")
local_comfy_temp = os.path.join(local_comfy_path, "temp")

# Name of the application
APP_NAME = os.path.basename(DIR_PATH)

# Command line to start the API server, e.g. "python3 ComfyUI/main.py"; warning: do not add parameter --port as it will be passed later
# API_COMMAND_LINE = '/tools/SITE/rnd/comfyUI/comfyui-1.0.3/bin/python3 /tools/SITE/rnd/comfyUI/comfyui-1.0.3/ComfyUI/main.py --disable-cuda-malloc'
API_COMMAND_LINE = "bash /tools/SITE/scripts/dncomfyui"

# URL of the API server (warning: do not add the port number to the URL as it will be passed later)
API_URL = "127.0.0.1"

# Set this to the maximum number of connection attempts to ComfyUI you want
MAX_COMFY_START_ATTEMPTS = 30

# The waiting time for each reattempt to connect to ComfyUI
COMFY_START_ATTEMPTS_SLEEP = 1

# Unique identifier for this instance of the worker; used in the WebSocket connection
INSTANCE_IDENTIFIER = APP_NAME + "-" + str(uuid.uuid4())
