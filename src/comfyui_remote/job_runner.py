from __future__ import absolute_import

from PyQt5.QtCore import QObject, pyqtSignal


import copy
import json
import os
import shutil
import threading
import logging
from typing import Optional

from comfyui_remote.config.settings_config import local_comfy_input
from comfyui_remote.executors.api_executor import ComfyConnector
from comfyui_remote.utils.cache_utils import (
    update_cache,
    transfer_imgs_from_path,
    get_first_frame,
    copy_matching_files,
    transfer_single_img,
    transfer_imgs_from_list,
    clean_input_dirs,
    iterate_through_files,
    get_folder_name,
)
from comfyui_remote.utils.common_utils import (
    display_command,
    has_extension,
    get_filenames_in_range,
    extract_paths,
    remove_extracted_paths,
    kill_comfy_instances,
)
from comfyui_remote.utils.json_utils import (
    load_json_data,
    get_dnfileout_version,
    search_params,
    update_values,
    modify_start_frame,
    json_publish_script,
    modify_dnloader,
    modify_fileout_folder_bool,
    remove_publisher,
)

logger = logging.getLogger(__name__)


class ExecuteWorkflow(QObject):
    progress_signal = pyqtSignal(int)  # Signal to emit GUI progress updates

    def __init__(
        self,
        json_file: str,
        batch_size: int = 1,
        comfyui_version: Optional[str] = None,
        frame_range: Optional[str] = None,
        int_args: Optional[str] = None,
        float_args: Optional[str] = None,
        str_args: Optional[str] = None,
    ):
        super().__init__()
        if os.environ.get("DEBUGC"):
            import sys

            sys.path.append(
                "/hosts/mtlws1638/user_data/venv/platform-pipe5-1/deployment/platform-pipe5-1/build/venv/lib/python3.9/site-packages"
            )
            import debugpy

            # debugpy.configure(python=r"/u/rafs/.pyenv/shims/python")
            debugpy.listen(5678)
            print("awaiting for client")
            debugpy.wait_for_client()
            debugpy.debug_this_thread()

        self.json_file = json_file
        self.batch_size = batch_size
        self.frame_range = frame_range

        self.progress = 0  # progress for GUI loading bar
        self._is_interrupted = threading.Event()

        self.input_dirs = []
        self.cache_dirs = []
        self.first_run = True

        self.json_data = load_json_data(self.json_file)
        self.comfyui_version = comfyui_version

        # Load optional arguments with default as empty dict
        self.int_args = self.load_json_safe(int_args, "integer") if int_args else {}
        self.float_args = self.load_json_safe(float_args, "float") if float_args else {}
        self.str_args = self.load_json_safe(str_args, "string") if str_args else {}

        self.params = {
            "int": search_params(self.json_data, "dnInteger"),
            "float": search_params(self.json_data, "dnFloat"),
            "str": search_params(self.json_data, "dnString"),
        }

        self.comfy_connector = None

    def load_json_safe(self, arg: Optional[str], arg_type: str):
        """Safely loads JSON and provides a custom error message."""
        try:
            return json.loads(arg) if arg else {}
        except json.JSONDecodeError:
            raise ValueError(
                f"Error in {arg_type} argument: Please ensure the string arguments are properly formatted with quotation marks."
            )

    def request_param_inputs(self, param, param_type) -> None:
        while True:
            value = input(f"Please enter value for {param} ({param_type}): ")
            if value.strip():  # Check if value is not empty or just spaces
                if param_type == "int":
                    self.int_args[param] = value
                elif param_type == "float":
                    self.float_args[param] = value
                elif param_type == "str":
                    self.str_args[param] = value
                break  # Exit the loop if a valid value is entered

    def check_duplicate_params(self):
        seen_params = set()
        for param_type, param_list in self.params.items():
            for param in param_list:
                if param in seen_params:
                    raise ValueError(f"Duplicate parameter found: {param}")
                else:
                    seen_params.add(param)

    def modify_json_with_params(self) -> None:
        """
        Modify JSON file with user prompts.

        Returns:
            dict: Modified JSON content.
        """
        if self.int_args:
            self.json_data = update_values(self.json_data, self.int_args)
        if self.float_args:
            self.json_data = update_values(self.json_data, self.float_args)
        if self.str_args:
            self.json_data = update_values(self.json_data, self.str_args)

    def run_api(
        self, modified_json, current_iteration, total_iterations, is_interrupted
    ) -> None:
        if not modified_json:
            raise ValueError("JSON data is not loaded or modified")
        logger.info("comfyui_version={}".format(self.comfyui_version))
        logger.info(
            display_command(
                self.input_dirs,
                self.json_file,
                self.batch_size,
                self.frame_range,
                self.int_args,
                self.float_args,
                self.str_args,
            )
        )
        self.comfy_connector = ComfyConnector(
            modified_json,
            self.comfyui_version,
            current_iteration,
            total_iterations,
            is_interrupted,
            self.progress,
            self.progress_signal,
        )
        # Always generate images for the actual workflow
        self.generate_imgs(modified_json, current_iteration, is_interrupted)
        # after generation, set first_run to False
        self.first_run = False

    def generate_imgs(self, modified_json, current_iteration, is_interrupted) -> None:
        self.comfy_connector.generate_images(
            modified_json, current_iteration, is_interrupted
        )

    def prepare_input(self) -> None:
        # Process each input directory
        for i in self.input_dirs:
            logger.info(f"i={i}")
            cache_dir = []  # Reset cache dirs for each input
            for key, path in i.items():
                # Update Cache folder
                cache_path = os.path.join(local_comfy_input, key)
                update_cache(cache_path)
                cache_dir.append(cache_path)
                self.cache_dirs.append(cache_path)
                if self.frame_range is None:
                    if not has_extension(path):
                        logger.info("1")
                        # Transfer all images from the directory
                        transfer_imgs_from_path(im_path=path, temp_dir=cache_path)
                        logger.info(f"path={path}")
                        # copy_matching_files(path, cache_path)
                        # Handle sequence frame range
                        start_frame = get_first_frame(cache_path)
                        modify_start_frame(self.json_data, start_frame)
                    elif "#" in path:
                        # Copy only the correct filenames with "####" over to cache path
                        copy_matching_files(path, cache_path)
                        # Handle sequence frame range
                        start_frame = get_first_frame(cache_path)
                        modify_start_frame(self.json_data, start_frame)
                    else:
                        logger.info("2")
                        # Handle single image path
                        transfer_single_img(path, cache_path)
                else:
                    logger.info("3")
                    start_frame, end_frame = self.frame_range.split("-")
                    start_frame = int(start_frame)
                    end_frame = int(end_frame)
                    modify_start_frame(self.json_data, start_frame)
                    # Ensure the start frame is less than or equal to the end frame
                    if start_frame > end_frame:
                        logger.warning(
                            "Error: Start frame must be less than or equal to end frame."
                        )
                        continue
                    input_filenames = get_filenames_in_range(
                        path, start_frame, end_frame
                    )
                    transfer_imgs_from_list(
                        im_list=input_filenames, temp_dir=cache_path
                    )

            return cache_path

    def execute(self, is_interrupted):
        self.check_duplicate_params()

        # prompt user input if not specified in CLI
        # for param_type, param_list in self.params.items():
        #     for param in param_list:
        #         if (
        #             param not in self.int_args
        #             and param not in self.float_args
        #             and param not in self.str_args
        #         ):
        #             self.request_param_inputs(param, param_type)

        # extract any paths from str args
        # this is if the entire workflow is just a string connected to a dnPublisher
        publishing_script = json_publish_script(self.json_data)
        if not publishing_script:
            self.input_dirs = extract_paths(self.str_args)
            if "#" not in self.input_dirs:
                clean_input_dirs(
                    self.input_dirs
                )  # removes filenames leaving just the directory path
            # remove any input strings from str_args so that we have them seperated
            self.str_args = remove_extracted_paths(self.str_args, self.input_dirs)
            modify_dnloader(self.json_data, True)
        # update user args
        self.modify_json_with_params()

        # update cache dirs
        cache_path = self.prepare_input()
        # self.input_dirs = extract_paths(self.str_args)
        # cache_path = self.input_dirs

        first_loop = True

        self.progress += 5
        self.progress_signal.emit(self.progress)

        if cache_path:
            total_files = 0
            for files in iterate_through_files(self.cache_dirs):
                total_files += 1
            total_iterations = int(total_files) * int(self.batch_size)
            current_iteration = 0

            if total_files == 1:
                self.progress += 35
                self.progress_signal.emit(self.progress)

            for batch_num in range(1, int(self.batch_size) + 1):
                for files in iterate_through_files(self.cache_dirs):
                    logger.info(f"is_interrupted={is_interrupted}")
                    if is_interrupted:
                        if is_interrupted():  # Dynamically check if interrupted
                            self.interrupt()
                            break
                    current_iteration += 1
                    in_args = {}
                    for file in files:
                        node_name = get_folder_name(file)
                        in_args[node_name] = file
                    self.json_data = update_values(self.json_data, in_args)
                    # Check if it's the first loop iteration
                    if first_loop:
                        # Run the function with True for the first time
                        modify_fileout_folder_bool(self.json_data, True)
                        first_loop = False  # Set the flag to False after the first run
                    else:
                        # Run the function with False for subsequent loops
                        modify_fileout_folder_bool(self.json_data, False)

                    # Check if this is the last iteration
                    if current_iteration != total_iterations:
                        if not publishing_script:
                            # Remove any dnPublisher nodes if its not the final iteration
                            json_data_copy = copy.deepcopy(self.json_data)
                            modified_json = remove_publisher(json_data_copy)
                    else:
                        modified_json = self.json_data
                    logger.debug(json.dumps(modified_json, indent=2))
                    self.run_api(
                        modified_json,
                        current_iteration,
                        total_iterations,
                        is_interrupted,
                    )

            # Clean TEMP Folder:
            for cache in self.cache_dirs:
                shutil.rmtree(cache)
        else:
            current_iteration = 0
            total_iterations = 1
            self.run_api(
                self.json_data, current_iteration, total_iterations, is_interrupted
            )
        if self.comfy_connector:
            self.comfy_connector.kill_api()
        kill_comfy_instances()
        # Signal completion progress
        self.progress = 100
        if self.progress_signal:
            self.progress_signal.emit(self.progress)
        logger.info(
            display_command(
                self.input_dirs,
                self.json_file,
                self.batch_size,
                self.frame_range,
                self.int_args,
                self.float_args,
                self.str_args,
            )
        )

    def interrupt(self):
        """Handle interruption logic."""
        self._is_interrupted.set()
        try:
            self.kill_api()
            kill_comfy_instances()
        except Exception:
            pass
