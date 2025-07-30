import os
import sys
import signal
import socket
import json
import urllib.request
import urllib.parse
from PIL import Image
import io
import requests
import threading
import time
import subprocess
import logging

from comfyui_remote.executors.websocket import WSProtoWrapper

# Get the absolute path of the package.
package_path = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
# This is done by inserting the local package path at the beginning of sys.path, which gives it precedence over installed packages.
if package_path not in sys.path:
    sys.path.insert(0, package_path)
from comfyui_remote.config import settings_config
from comfyui_remote.utils.common_utils import kill_comfy_instances

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
        # debugpy.debug_this_thread()
        if not hasattr(self, "initialized"):
            self.json_file = json_file
            self.comfyui_version = comfyui_version
            self.urlport = self.find_available_port()
            self.server_address = f"http://{settings_config.API_URL}:{self.urlport}"
            self.client_id = settings_config.INSTANCE_IDENTIFIER
            self.ws_address = f"ws://{settings_config.API_URL}:{self.urlport}/ws?clientId={self.client_id}"
            self.ws = WSProtoWrapper()  # Use our wsproto wrapper
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
        logger.info(f"second emit of 5% = {self.progress}%")
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
                logger.info("api_command_line={}".format(api_command_line))
            else:
                api_command_line = (
                    settings_config.API_COMMAND_LINE + f" --port {self.urlport}"
                )  # Add the port to the command line
            if (
                self._process is None or self._process.poll() is not None
            ):  # Check if the process is not running or has terminated for some reason
                # Log additional debugging information
                logger.info(f"Starting API process with command: {api_command_line}")
                logger.info(f"Current working directory: {os.getcwd()}")

                # Store command for debugging
                self._last_command = api_command_line

                try:
                    # For bash scripts, we need to handle the case where the script might exit early
                    # Let's run with explicit bash and capture more environment information
                    cmd_parts = api_command_line.split()
                    if cmd_parts[0] == "bash" and len(cmd_parts) > 1:
                        # This is a bash script, run it with better error handling
                        script_path = cmd_parts[1]
                        script_args = cmd_parts[2:] if len(cmd_parts) > 2 else []

                        # Test if the script exists and is executable
                        if not os.path.exists(script_path):
                            # Try to find it in PATH or relative to current directory
                            potential_paths = [
                                os.path.join(os.getcwd(), script_path),
                                os.path.join(
                                    os.path.dirname(__file__),
                                    "..",
                                    "..",
                                    "..",
                                    "bin",
                                    script_path,
                                ),
                            ]
                            for path in potential_paths:
                                if os.path.exists(path):
                                    script_path = path
                                    logger.info(f"Found script at: {script_path}")
                                    break
                            else:
                                logger.error(
                                    f"Script not found: {script_path} in any of {potential_paths}"
                                )

                        # Run with explicit bash and capture exit codes
                        full_command = ["bash", "-x", script_path] + script_args
                        logger.info(f"Executing with explicit bash: {full_command}")

                        self._process = subprocess.Popen(
                            full_command,
                            preexec_fn=os.setsid,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            bufsize=1,
                        )
                    else:
                        # Not a bash script, run normally
                        self._process = subprocess.Popen(
                            api_command_line.split(),
                            preexec_fn=os.setsid,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            bufsize=1,
                        )

                    logger.info("API process started with PID: %s", self._process.pid)

                    # Immediately check if the process is still alive
                    time.sleep(0.1)  # Give it a moment
                    exit_code = self._process.poll()
                    if exit_code is not None:
                        logger.error(
                            f"Process immediately exited with code: {exit_code}"
                        )
                    else:
                        logger.info("Process appears to be running after initial check")

                except Exception as e:
                    logger.error(f"Failed to start API process: {e}")
                    raise

                # Initialize output capture for error reporting
                self._captured_stdout = []
                self._captured_stderr = []

                # Start threads to stream and capture output
                self._stdout_thread = threading.Thread(
                    target=self._stream_output,
                    args=(self._process.stdout, "STDOUT", self._captured_stdout),
                    daemon=True,
                )
                self._stderr_thread = threading.Thread(
                    target=self._stream_output,
                    args=(self._process.stderr, "STDERR", self._captured_stderr),
                    daemon=True,
                )
                self._stdout_thread.start()
                self._stderr_thread.start()

                self.wait_for_api_to_start(is_interrupted)

    def _stream_output(self, pipe, stream_type, capture_list):
        """Stream process output to logger while capturing it for error reporting."""
        try:
            for line in iter(pipe.readline, ""):
                if line:
                    line = line.rstrip("\n\r")
                    # Log the output using the logger
                    # ComfyUI writes normal output to STDERR, so treat both as INFO unless it's clearly an error
                    if any(
                        error_indicator in line.lower()
                        for error_indicator in [
                            "error",
                            "failed",
                            "exception",
                            "traceback",
                        ]
                    ):
                        logger.error(f"ComfyUI {stream_type}: {line}")
                    else:
                        logger.info(f"ComfyUI {stream_type}: {line}")
                    # Also capture for error reporting
                    capture_list.append(line)
        except Exception as e:
            logger.error(f"Error streaming {stream_type}: {e}")
        finally:
            pipe.close()

    def wait_for_api_to_start(self, is_interrupted):
        attempts = 0
        while not self.is_api_running(
            is_interrupted
        ):  # Block execution until the API server is running
            if is_interrupted != False:
                if is_interrupted():  # Dynamically check if interrupted
                    self.interrupt()
                    break

            # Check if the process has terminated with an error
            if self._process is not None:
                exit_code = self._process.poll()
                if exit_code is not None and exit_code != 0:
                    # Process has terminated with a non-zero exit code
                    # Wait a bit for output threads to capture final messages
                    time.sleep(0.5)

                    # Log the error but don't immediately fail - enroot errors might be non-fatal
                    error_msg = f"API startup script exited with code {exit_code}."
                    if hasattr(self, "_captured_stderr") and self._captured_stderr:
                        stderr_output = "\n".join(
                            self._captured_stderr[-10:]
                        )  # Last 10 lines
                        error_msg += f" Error output: {stderr_output}"
                    else:
                        error_msg += " No error output captured."
                    if hasattr(self, "_captured_stdout") and self._captured_stdout:
                        stdout_output = "\n".join(
                            self._captured_stdout[-10:]
                        )  # Last 10 lines
                        error_msg += f" Standard output: {stdout_output}"
                    else:
                        error_msg += " No standard output captured."

                    # Additional debugging for farm environment
                    logger.warning(f"Process exit debugging info:")
                    logger.warning(
                        f"  - Process PID: {self._process.pid if self._process else 'None'}"
                    )
                    logger.warning(f"  - Exit code: {exit_code}")
                    logger.warning(
                        f"  - Command executed: {getattr(self, '_last_command', 'Unknown')}"
                    )
                    logger.warning(f"  - Working directory: {os.getcwd()}")

                    logger.warning(
                        f"Process exited early but continuing to check API availability: {error_msg}"
                    )

                    # Only fail immediately if we've tried for a reasonable number of attempts
                    # This allows for enroot initialization errors that don't prevent ComfyUI from starting
                    if attempts >= (settings_config.MAX_COMFY_START_ATTEMPTS // 2):
                        self.kill_api()
                        kill_comfy_instances()
                        raise RuntimeError(
                            f"API startup script failed after process exit and {attempts} attempts. {error_msg}"
                        )

            if attempts >= settings_config.MAX_COMFY_START_ATTEMPTS:
                # Get process output for debugging if available
                error_msg = f"API startup procedure failed after {attempts} attempts."
                if hasattr(self, "_captured_stderr") and self._captured_stderr:
                    stderr_output = "\n".join(
                        self._captured_stderr[-10:]
                    )  # Last 10 lines
                    error_msg += f" Error output: {stderr_output}"
                if hasattr(self, "_captured_stdout") and self._captured_stdout:
                    stdout_output = "\n".join(
                        self._captured_stdout[-10:]
                    )  # Last 10 lines
                    error_msg += f" Standard output: {stdout_output}"

                self.kill_api()
                kill_comfy_instances()
                raise RuntimeError(error_msg)

            time.sleep(
                settings_config.COMFY_START_ATTEMPTS_SLEEP
            )  # Wait before checking again, for 1 second by default
            attempts += 1  # Increment the number of attempts
        pid_info = f"PID {self._process.pid}" if self._process else "no active process"
        logger.info(
            f"API startup procedure finalized after {attempts} attempts with {pid_info} in port {self.urlport}"
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
        return False

    def kill_api(self):
        # This method kills the API server process, closes the WebSocket connection, and resets instance-specific attributes.
        try:
            # Close WebSocket connection first, before killing the process
            if self.ws and self.ws.connected:
                self.ws.close()
                logger.info("kill_api: WebSocket connection closed.")
                # Give a short delay for the close handshake to complete
                time.sleep(0.1)

            # Then kill the API process
            if self._process is not None and self._process.poll() is None:
                os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
                logger.info("kill_api: API process group killed.")
        except Exception as e:
            logger.error(f"kill_api: Warning: The following issues occurred: {e}")
        finally:
            # Clean up output streaming threads
            if hasattr(self, "_stdout_thread") and self._stdout_thread.is_alive():
                try:
                    self._stdout_thread.join(timeout=1.0)
                except Exception:
                    pass
            if hasattr(self, "_stderr_thread") and self._stderr_thread.is_alive():
                try:
                    self._stderr_thread.join(timeout=1.0)
                except Exception:
                    pass

            self._process = None
            self.ws = None
            self.urlport = None
            self.server_address = None
            self.client_id = None
            # Clean up capture lists
            if hasattr(self, "_captured_stdout"):
                self._captured_stdout = None
            if hasattr(self, "_captured_stderr"):
                self._captured_stderr = None
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

                # Receive WebSocket message with timeout
                try:
                    out = self.ws.recv(timeout=30.0)  # 30 second timeout
                except TimeoutError:
                    logger.warning("WebSocket receive timeout, continuing...")
                    continue

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
            # try:
            #     if output_node == "dnFileOut":
            #         filenames = eval(f"history['outputs']{address}")[
            #             "images"
            #         ]  # Extract all images
            #         logger.info(f"Extracted images: {filenames}")

            #     else:
            #         filenames = eval(f"history['outputs']{address}")[
            #             "images"
            #         ]  # Extract all images
            #         logger.info(f"extracted filenames={filenames}")

            # except Exception as e:  # Handle the inner try block error
            #     logger.error(f"Error parsing address or extracting images: {e}")
            #     return []
            images = []  # Initialize images list outside the inner try block

            # for img_info in filenames:
            #     filename = img_info["filename"]
            #     subfolder = img_info["subfolder"]
            #     folder_type = img_info["type"]
            #     image_data = self.get_image(filename, subfolder, folder_type)
            #     image_file = io.BytesIO(image_data)
            #     image = Image.open(image_file)
            #     images.append(image)

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
            class_type = json_object.get(
                "class_type"
            )  # Fixed: was using undefined 'value'
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
        if self.ws and self.ws.connected:
            self.kill_api()
            kill_comfy_instances()
