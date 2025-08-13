import json
import logging
import os
import platform
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

import requests

from comfyui_remote.executors.websocket import WSProtoWrapper

# Get the absolute path of the package.
package_path = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
# This is done by inserting the local package path at the beginning of sys.path, which gives it precedence over installed packages.
if package_path not in sys.path:
    sys.path.insert(0, package_path)
from comfyui_remote import config
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
        if not hasattr(self, "initialized"):
            self.json_file = json_file
            self.comfyui_version = comfyui_version
            self.urlport = self.find_available_port()
            self.server_address = f"http://{config.API_URL}:{self.urlport}"
            self.client_id = config.INSTANCE_IDENTIFIER
            self.ws_address = (
                f"ws://{config.API_URL}:{self.urlport}/ws?clientId={self.client_id}"
            )
            self.ws = WSProtoWrapper()
            self.current_iteration = current_iteration
            self.total_iterations = total_iterations
            self.progress = progress
            self.progress_signal = progress_signal
            self._is_interrupted = threading.Event()
            self.start_api(is_interrupted)
            self.initialized = True

    def find_available_port(self):
        """
        Find an available port for the API server if the initial port is in use.

        Returns:
            int: An available port number
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    def start_api(self, is_interrupted):
        """Start the API server process and wait for it to become available."""
        self.progress += 5
        self.progress_signal.emit(self.progress)

        if not self.is_api_running(is_interrupted):
            if is_interrupted != False:
                if is_interrupted():  # Dynamically check if interrupted
                    self.interrupt()

            if self.comfyui_version:
                api_command_line = (
                    config.API_COMMAND_LINE
                    + f" --version {self.comfyui_version}"
                    + f" --port {self.urlport}"
                )
                logger.info("api_command_line={}".format(api_command_line))
            else:
                api_command_line = config.API_COMMAND_LINE + f" --port {self.urlport}"
            if self._process is None or self._process.poll() is not None:
                logger.info(f"Starting API process with command: {api_command_line}")
                logger.info(f"Current working directory: {os.getcwd()}")

                self._last_command = api_command_line

                try:
                    # Handle bash scripts with better error handling
                    cmd_parts = api_command_line.split()
                    if cmd_parts[0] == "bash" and len(cmd_parts) > 1:
                        script_path = cmd_parts[1]
                        script_args = cmd_parts[2:] if len(cmd_parts) > 2 else []

                        if not os.path.exists(script_path):
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

                        full_command = ["bash", "-x", script_path] + script_args
                        logger.info(f"Executing with explicit bash: {full_command}")
                        kwargs = dict(
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            bufsize=1,
                        )

                        if platform.system() == "Windows":
                            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                        else:
                            kwargs["preexec_fn"] = os.setsid

                        self._process = subprocess.Popen(full_command, **kwargs)



                    else:

                        kwargs = dict(

                            stdout=subprocess.PIPE,

                            stderr=subprocess.PIPE,

                            text=True,

                            bufsize=1,

                        )

                        if platform.system() == "Windows":

                            # Run the .bat via cmd; start in a new process group so we can signal it

                            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

                            kwargs["shell"] = True  # needed to execute comfyui.bat

                            cmd = api_command_line  # string for shell=True

                        else:

                            kwargs["preexec_fn"] = os.setsid  # POSIX process group

                            cmd = api_command_line.split()  # list for shell=False

                        self._process = subprocess.Popen(cmd, **kwargs)

                    logger.info("API process started with PID: %s", self._process.pid)

                    time.sleep(0.1)
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

                self._captured_stdout = []
                self._captured_stderr = []

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
                    capture_list.append(line)
        except Exception as e:
            logger.error(f"Error streaming {stream_type}: {e}")
        finally:
            pipe.close()

    def wait_for_api_to_start(self, is_interrupted):
        """Wait for the API server to start up."""
        attempts = 0
        while not self.is_api_running(is_interrupted):
            if is_interrupted != False:
                if is_interrupted():
                    self.interrupt()
                    break

            if self._process is not None:
                exit_code = self._process.poll()
                if exit_code is not None and exit_code != 0:
                    time.sleep(0.5)

                    error_msg = f"API startup script exited with code {exit_code}."
                    if hasattr(self, "_captured_stderr") and self._captured_stderr:
                        stderr_output = "\n".join(self._captured_stderr[-10:])
                        error_msg += f" Error output: {stderr_output}"
                    else:
                        error_msg += " No error output captured."
                    if hasattr(self, "_captured_stdout") and self._captured_stdout:
                        stdout_output = "\n".join(self._captured_stdout[-10:])
                        error_msg += f" Standard output: {stdout_output}"
                    else:
                        error_msg += " No standard output captured."

                    logger.warning(
                        f"Process exited early but continuing to check API availability: {error_msg}"
                    )

                    # Only fail immediately if we've tried for a reasonable number of attempts
                    # This allows for enroot initialization errors that don't prevent ComfyUI from starting
                    if attempts >= (config.MAX_COMFY_START_ATTEMPTS):
                        self.kill_api()
                        kill_comfy_instances()
                        raise RuntimeError(
                            f"API startup script failed after process exit and {attempts} attempts. {error_msg}"
                        )

            if attempts >= config.MAX_COMFY_START_ATTEMPTS:
                error_msg = f"API startup procedure failed after {attempts} attempts."
                if hasattr(self, "_captured_stderr") and self._captured_stderr:
                    stderr_output = "\n".join(self._captured_stderr[-10:])
                    error_msg += f" Error output: {stderr_output}"
                if hasattr(self, "_captured_stdout") and self._captured_stdout:
                    stdout_output = "\n".join(self._captured_stdout[-10:])
                    error_msg += f" Standard output: {stdout_output}"

                self.kill_api()
                kill_comfy_instances()
                raise RuntimeError(error_msg)

            time.sleep(config.COMFY_START_ATTEMPTS_SLEEP)
            attempts += 1

        pid_info = f"PID {self._process.pid}" if self._process else "no active process"
        logger.info(
            f"API startup procedure finalized after {attempts} attempts with {pid_info} in port {self.urlport}"
        )
        time.sleep(0.5)

    def is_api_running(self, is_interrupted):
        """Check if the API server is running and responsive."""
        try:
            if is_interrupted != False:
                if is_interrupted():
                    self.interrupt()

            logger.info(f"Checking web server is running in {self.server_address}...")
            response = requests.get(self.server_address)
            if response.status_code == 200:
                self.ws.connect(self.ws_address)
                logger.info(
                    "Web server is running (status code 200). Trying test image..."
                )
                test_image = self.generate_images(
                    self.json_file, self.current_iteration, is_interrupted
                )
                logger.info(f"Type of test_image: {type(test_image)}")
                logger.info(f"Test image: {test_image}")
                return test_image is not None
        except Exception:
            pass
        return False

    def kill_api(self):
        """Cross-platform shutdown of the ComfyUI process + WS, with cleanup."""
        import platform, signal, time, os

        try:
            # 1) Close WebSocket first (gives the server a chance to finish nicely)
            if getattr(self, "ws", None) and getattr(self.ws, "connected", False):
                try:
                    self.ws.close()
                    logger.info("kill_api: WebSocket connection closed.")
                except Exception as e:
                    logger.warning(f"kill_api: WS close warning: {e}")
                time.sleep(0.1)  # brief handshake time

            # 2) Stop the spawned process
            if self._process is not None and self._process.poll() is None:
                try:
                    if platform.system() == "Windows":
                        # Send CTRL+BREAK to the process group, then terminate, then kill as last resort
                        try:
                            self._process.send_signal(signal.CTRL_BREAK_EVENT)
                        except Exception:
                            pass
                        time.sleep(0.3)
                        try:
                            self._process.terminate()
                        except Exception:
                            pass
                        try:
                            self._process.wait(timeout=2.0)
                        except Exception:
                            try:
                                self._process.kill()
                            except Exception:
                                pass
                        logger.info("kill_api: Windows process group signaled/terminated.")
                    else:
                        # POSIX: terminate the whole group
                        try:
                            os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
                        except Exception:
                            # Fallback to terminate/kill if killpg fails
                            try:
                                self._process.terminate()
                            except Exception:
                                pass
                        try:
                            self._process.wait(timeout=2.0)
                        except Exception:
                            try:
                                self._process.kill()
                            except Exception:
                                pass
                        logger.info("kill_api: POSIX process group signaled/terminated.")
                except Exception as e:
                    logger.error(f"kill_api: Warning during process shutdown: {e}")

        finally:
            # 3) Join output threads so pipes close cleanly
            try:
                if hasattr(self, "_stdout_thread") and self._stdout_thread.is_alive():
                    self._stdout_thread.join(timeout=1.0)
            except Exception:
                pass
            try:
                if hasattr(self, "_stderr_thread") and self._stderr_thread.is_alive():
                    self._stderr_thread.join(timeout=1.0)
            except Exception:
                pass

            # 4) Null out references
            self._process = None
            self.ws = None
            self.urlport = None
            self.server_address = None
            self.client_id = None

            if hasattr(self, "_captured_stdout"):
                self._captured_stdout = None
            if hasattr(self, "_captured_stderr"):
                self._captured_stderr = None

            # Reset singleton so a fresh ComfyConnector can start later
            ComfyConnector._instance = None
            logger.info("kill_api: Cleanup complete.")

    def get_history(self, prompt_id):
        """Get execution history for a specific prompt ID."""
        with urllib.request.urlopen(
            f"{self.server_address}/history/{prompt_id}"
        ) as response:
            return json.loads(response.read())

    def get_image(self, filename, subfolder, folder_type):
        """Retrieve an image from the API server."""
        data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        url_values = urllib.parse.urlencode(data)
        with urllib.request.urlopen(
            f"{self.server_address}/view?{url_values}"
        ) as response:
            return response.read()

    def queue_prompt(self, prompt):
        """Queue a prompt for execution on the ComfyUI server."""
        p = {"prompt": prompt, "client_id": self.client_id}
        data = json.dumps(p).encode("utf-8")
        headers = {"Content-Type": "application/json"}
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
        """Generate images using the ComfyUI API with the provided payload."""
        try:
            if not self.ws.connected:
                logger.info("WebSocket is not connected. Reconnecting...")
                self.ws.connect(self.ws_address)

            prompt_id = self.queue_prompt(payload)["prompt_id"]

            while True:
                if is_interrupted != False:
                    if is_interrupted():
                        self.interrupt()
                        break

                try:
                    out = self.ws.recv(timeout=30.0)
                except TimeoutError:
                    logger.warning("WebSocket receive timeout, continuing...")
                    continue

                if isinstance(out, str):
                    message = json.loads(out)
                    if message["type"] == "executing":
                        data = message["data"]
                        if data["node"] is None and data["prompt_id"] == prompt_id:
                            break

            # Update progress
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
            _, _, exc_traceback = sys.exc_info()
            line_no = exc_traceback.tb_lineno if exc_traceback else "unknown"
            error_message = f"Unhandled error at line {line_no}: {str(e)}"
            logger.error("generate_images - %s", error_message)
            self.kill_api()
            kill_comfy_instances()

    def upload_image(self, filepath, subfolder=None, folder_type=None, overwrite=False):
        """Upload an image to the API server for use in img2img or controlnet."""
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
        except Exception:
            raise

    @staticmethod
    def find_output_node(json_object):
        """Find the node containing the SaveImage class in a prompt."""
        for key, value in json_object.items():
            if isinstance(value, dict):
                if value.get("class_type") in {"SaveImage", "dnFileOut", "dnSaveImage"}:
                    return f"['{key}']"
                result = ComfyConnector.find_output_node(value)
                if result:
                    return result
        return None

    @staticmethod
    def load_payload(path):
        """Load a JSON payload from file."""
        with open(path, "r") as file:
            return json.load(file)

    @staticmethod
    def replace_key_value(
        json_object, target_key, new_value, class_type_list=None, exclude=True
    ):
        """Edit the payload of a prompt by replacing key values based on class type filters."""
        if isinstance(json_object, dict):
            class_type = json_object.get("class_type")
            should_apply_logic = (
                exclude
                and (class_type_list is None or class_type not in class_type_list)
            ) or (
                not exclude
                and (class_type_list is not None and class_type in class_type_list)
            )

            if should_apply_logic and target_key in json_object:
                json_object[target_key] = new_value

            for value in json_object.values():
                ComfyConnector.replace_key_value(
                    value, target_key, new_value, class_type_list, exclude
                )
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
