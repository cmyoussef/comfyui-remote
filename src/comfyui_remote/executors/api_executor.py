import os
import sys

# Get the absolute path of the package.
package_path = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
# This is done by inserting the local package path at the beginning of sys.path, which gives it precedence over installed packages.
if package_path not in sys.path:
    sys.path.insert(0, package_path)
from ComfyUI_remote.config import settings_config
from ComfyUI_remote.utils.common_utils import kill_comfy_instances
import socket
import json
import urllib.request
import urllib.parse
from PIL import Image
from websocket import (
    WebSocket,
)  # note: websocket-client (https://github.com/websocket-client/websocket-client)
import io
import requests
import threading
import time
import os
import subprocess
from typing import List
import sys
import logging
import ast

os.environ["PYTHONPATH"] = ""

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ComfyConnector:
    """
    A class to manage the connection and interaction with the ComfyUI API.
    """

    _instance = None
    _process = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ComfyConnector, cls).__new__(cls)
        return cls._instance

    def __init__(
        self,
        json_file,
        comfyui_version,
        current_iteration,
        total_iterations,
        is_interrupted,
        progress=0,
        progress_signal=None,
    ):
        """
        Initializes the ComfyConnector, starting the API server if necessary.
        """
        if not hasattr(self, "initialized"):
            self.json_file = json_file
            self.comfyui_version = comfyui_version
            self.urlport = self.find_available_port()
            self.server_address = f"http://{settings_config.API_URL}:{self.urlport}"
            self.client_id = settings_config.INSTANCE_IDENTIFIER
            self.ws_address = f"ws://{settings_config.API_URL}:{self.urlport}/ws?clientId={self.client_id}"
            self.ws = WebSocket()
            self.current_iteration = current_iteration
            self.total_iterations = total_iterations
            self.progress = progress
            self.progress_signal = progress_signal
            self._is_interrupted = threading.Event()
            self.start_api(is_interrupted)
            self.initialized = True

    def find_available_port(
        self,
    ):  # If the initial port is already in use, this method finds an available port to start the API server on
        """
        Uses socket to check for an available port
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    def start_api(self, is_interrupted):  # This method is used to start the API server
        self.progress += 5
        self.progress_signal.emit(self.progress)
        print(f"second emit of 5% = {self.progress}%")
        if not self.is_api_running(
            is_interrupted
        ):  # Block execution until the API server is running
            if is_interrupted != False:
                if is_interrupted():  # Dynamically check if interrupted
                    self.interrupt()

            if self.comfyui_version:
                api_command_line = (
                    settings_config.API_COMMAND_LINE
                    + f" --version {self.comfyui_version}"
                    + f" --port {self.urlport}"
                )  # Add the port to the command line
                print("api_command_line={}".format(api_command_line))
            else:
                api_command_line = (
                    settings_config.API_COMMAND_LINE + f" --port {self.urlport}"
                )  # Add the port to the command line
            if (
                self._process is None or self._process.poll() is not None
            ):  # Check if the process is not running or has terminated for some reason
                self._process = subprocess.Popen(api_command_line.split())
                logger.info("API process started with PID: %s", self._process.pid)
                self.wait_for_api_to_start(is_interrupted)

    def wait_for_api_to_start(self, is_interrupted):
        attempts = 0
        while not self.is_api_running(
            is_interrupted
        ):  # Block execution until the API server is running
            if is_interrupted != False:
                if is_interrupted():  # Dynamically check if interrupted
                    self.interrupt()
                    break
            if attempts >= settings_config.MAX_COMFY_START_ATTEMPTS:
                raise RuntimeError(
                    f"API startup procedure failed after {attempts} attempts."
                )
                self.kill_api()
                kill_comfy_instances()
            time.sleep(
                settings_config.COMFY_START_ATTEMPTS_SLEEP
            )  # Wait before checking again, for 1 second by default
            attempts += 1  # Increment the number of attempts
        logger.info(
            f"API startup procedure finalized after {attempts} attempts with PID {self._process.pid} in port {self.urlport}"
        )
        time.sleep(0.5)  # Wait for 0.5 seconds before returning

    def is_api_running(
        self, is_interrupted
    ):  # This method is used to check if the API server is running
        try:
            if is_interrupted != False:
                if is_interrupted():  # Dynamically check if interrupted
                    self.interrupt()

            logger.info(f"Checking web server is running in {self.server_address}...")
            response = requests.get(self.server_address)
            if (
                response.status_code == 200
            ):  # Check if the API server tells us it's running by returning a 200 status code
                self.ws.connect(self.ws_address)
                logger.info(
                    f"Web server is running (status code 200). Now trying test image..."
                )
                test_image = self.generate_images(
                    self.json_file, self.current_iteration, is_interrupted
                )  # settings_config.TEST_PAYLOAD
                logger.info(f"Type of test_image: {type(test_image)}")
                logger.info(f"Test image: {test_image}")
                return (
                    test_image is not None
                )  # this ensures that the API server is actually running and not just the web server
        except Exception as e:
            pass
            # logger.error("API not running:", e)
        return False

    def kill_api(self):
        # This method kills the API server process, closes the WebSocket connection, and resets instance-specific attributes.
        try:
            if self._process is not None and self._process.poll() is None:
                self._process.kill()
                logger.info("kill_api: API process killed.")
            if self.ws and self.ws.connected:
                self.ws.close()
                logger.info("kill_api: WebSocket connection closed.")
        except Exception as e:
            logger.error(f"kill_api: Warning: The following issues occurred: {e}")
        finally:
            self._process = None
            self.ws = None
            self.urlport = None
            self.server_address = None
            self.client_id = None
            ComfyConnector._instance = None
            logger.info("kill_api: Cleanup complete.")

    def get_history(
        self, prompt_id
    ):  # This method is used to retrieve the history of a prompt from the API server
        with urllib.request.urlopen(
            f"{self.server_address}/history/{prompt_id}"
        ) as response:
            return json.loads(response.read())

    def get_image(
        self, filename, subfolder, folder_type
    ):  # This method is used to retrieve an image from the API server
        data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        url_values = urllib.parse.urlencode(data)
        with urllib.request.urlopen(
            f"{self.server_address}/view?{url_values}"
        ) as response:
            return response.read()

    def queue_prompt(
        self, prompt
    ):  # This method is used to queue a prompt for execution
        p = {"prompt": prompt, "client_id": self.client_id}
        data = json.dumps(p).encode("utf-8")
        headers = {"Content-Type": "application/json"}  # Set Content-Type header
        req = urllib.request.Request(
            f"{self.server_address}/prompt", data=data, headers=headers
        )
        return json.loads(urllib.request.urlopen(req).read())

    def get_output_node(self, payload):
        for key, value in payload.items():
            if isinstance(value, dict):
                if value.get("class_type") in {"SaveImage", "dnFileOut", "dnSaveImage"}:
                    return value.get("class_type")

    def generate_images(self, payload, current_iteration, is_interrupted):
        try:
            if not self.ws.connected:
                logger.info("WebSocket is not connected. Reconnecting...")
                self.ws.connect(self.ws_address)

            prompt_id = self.queue_prompt(payload)["prompt_id"]

            while True:
                if is_interrupted != False:
                    if is_interrupted():  # Dynamically check if interrupted
                        self.interrupt()
                        break
                out = self.ws.recv()
                if isinstance(out, str):
                    message = json.loads(out)
                    if message["type"] == "executing":
                        data = message["data"]
                        if data["node"] is None and data["prompt_id"] == prompt_id:
                            break

            address = self.find_output_node(payload)
            history = self.get_history(prompt_id)[prompt_id]
            output_node = self.get_output_node(payload)
            loop_progress = (
                current_iteration / self.total_iterations * (100 - self.progress)
            ) + self.progress
            self.progress_signal.emit(loop_progress)
            try:
                if output_node == "dnFileOut":
                    filenames = eval(f"history['outputs']{address}")[
                        "images"
                    ]  # Extract all images
                    print(f"Extracted images: {parsed_address['ui']['images']}")

                else:
                    filenames = eval(f"history['outputs']{address}")[
                        "images"
                    ]  # Extract all images
                    print(f"extracted filenames={filenames}")

            except Exception as e:  # Handle the inner try block error
                # logger.error(f"Error parsing address or extracting images: {e}")
                return []
            images = []  # Initialize images list outside the inner try block

            for img_info in filenames:
                filename = img_info["filename"]
                subfolder = img_info["subfolder"]
                folder_type = img_info["type"]
                image_data = self.get_image(filename, subfolder, folder_type)
                image_file = io.BytesIO(image_data)
                image = Image.open(image_file)
                images.append(image)

            return images

        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            line_no = exc_traceback.tb_lineno
            error_message = f"Unhandled error at line {line_no}: {str(e)}"
            logger.error("generate_images - %s", error_message)
            self.kill_api()
            kill_comfy_instances()

    def upload_image(
        self, filepath, subfolder=None, folder_type=None, overwrite=False
    ):  # This method is used to upload an image to the API server for use in img2img or controlnet
        try:
            url = f"{self.server_address}/upload/image"
            with open(filepath, "rb") as file:
                files = {"image": file}
                data = {"overwrite": str(overwrite).lower()}
                if subfolder:
                    data["subfolder"] = subfolder
                if folder_type:
                    data["type"] = folder_type
                response = requests.post(url, files=files, data=data)
            return response.json()
        except Exception as e:
            raise

    @staticmethod
    def find_output_node(
        json_object,
    ):  # This method is used to find the node containing the SaveImage class in a prompt
        for key, value in json_object.items():
            if isinstance(value, dict):
                if value.get("class_type") in {"SaveImage", "dnFileOut", "dnSaveImage"}:
                    return f"['{key}']"  # Return the key containing the SaveImage class
                result = ComfyConnector.find_output_node(value)
                if result:
                    return result
        return None

    @staticmethod
    def load_payload(path):
        with open(path, "r") as file:
            return json.load(file)

    @staticmethod
    def replace_key_value(
        json_object, target_key, new_value, class_type_list=None, exclude=True
    ):  # This method is used to edit the payload of a prompt
        # Check if the current value is a dictionary and apply the logic recursively
        if isinstance(json_object, dict):
            class_type = value.get("class_type")
            # Determine whether to apply the logic based on exclude and class_type_list
            should_apply_logic = (
                exclude
                and (class_type_list is None or class_type not in class_type_list)
            ) or (
                not exclude
                and (class_type_list is not None and class_type in class_type_list)
            )
            # Apply the logic to replace the target key with the new value if conditions are met
            if should_apply_logic and target_key in json_object:
                json_object[target_key] = new_value
            # Recurse vertically (into nested dictionaries)
            for value in json_object.values():
                ComfyConnector.replace_key_value(
                    value, target_key, new_value, class_type_list, exclude
                )
        # Recurse sideways (into lists)
        elif isinstance(json_object, list):
            for item in json_object:
                ComfyConnector.replace_key_value(
                    item, target_key, new_value, class_type_list, exclude
                )

    def interrupt(self):
        """Handle interruption logic."""
        self._is_interrupted.set()
        if self.is_api_running:
            self.kill_api()
            kill_comfy_instances()
