from __future__ import absolute_import

import copy
import json
import logging
import os
import shutil
import threading
from typing import Optional, List, Dict

from PyQt5.QtCore import QObject, pyqtSignal

from comfyui_remote.config import local_comfy_input
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
    has_extension,
    get_filenames_in_range,
    extract_paths,
    remove_extracted_paths,
    kill_comfy_instances,
)
from comfyui_remote.utils.json_utils import (
    load_json_data,
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
    """
    Workflow executor for ComfyUI that manages batch processing, progress tracking, and input handling.

    This class handles the execution of ComfyUI workflows with support for:
    - Batch processing with configurable batch sizes
    - Frame range processing for image sequences
    - Parameter injection (int, float, string arguments)
    - Progress tracking via Qt signals
    - Input directory caching and cleanup
    - Workflow interruption handling
    """

    progress_signal = pyqtSignal(int)

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
        self.json_file = json_file
        self.batch_size = batch_size
        self.frame_range = frame_range

        self.progress = 0
        self._is_interrupted = threading.Event()

        self.input_dirs: List[Dict[str, str]] = []
        self.cache_dirs: List[str] = []
        self.first_run = True

        self.json_data = load_json_data(self.json_file)
        self.comfyui_version = comfyui_version

        self.int_args = self.load_json_safe(int_args, "integer") if int_args else {}
        self.float_args = self.load_json_safe(float_args, "float") if float_args else {}
        self.str_args = self.load_json_safe(str_args, "string") if str_args else {}

        self.params = {
            "int": search_params(self.json_data, "dnInteger"),
            "float": search_params(self.json_data, "dnFloat"),
            "str": search_params(self.json_data, "dnString"),
        }

        self.comfy_connector: Optional[ComfyConnector] = None

    def load_json_safe(self, arg: Optional[str], arg_type: str):
        """Safely loads JSON and provides a custom error message."""
        try:
            return json.loads(arg) if arg else {}
        except json.JSONDecodeError:
            raise ValueError(
                f"Error in {arg_type} argument: Please ensure the string arguments are properly formatted with quotation marks."
            )

    def check_duplicate_params(self):
        """Check for duplicate parameters across different parameter types and raise an error if found."""
        seen_params = set()
        for param_type, param_list in self.params.items():
            for param in param_list:
                if param in seen_params:
                    raise ValueError(f"Duplicate parameter found: {param}")
                else:
                    seen_params.add(param)

    def modify_json_with_params(self) -> None:
        """Update JSON data with user-provided integer, float, and string arguments."""
        if self.int_args:
            self.json_data = update_values(self.json_data, self.int_args)
        if self.float_args:
            self.json_data = update_values(self.json_data, self.float_args)
        if self.str_args:
            self.json_data = update_values(self.json_data, self.str_args)

    def run_api(
        self, modified_json, current_iteration, total_iterations, is_interrupted
    ) -> None:
        """Initialize ComfyConnector and run the workflow generation process."""
        if not modified_json:
            raise ValueError("JSON data is not loaded or modified")

        self.comfy_connector = ComfyConnector(
            modified_json,
            self.comfyui_version,
            current_iteration,
            total_iterations,
            is_interrupted,
            self.progress,
            self.progress_signal,
        )
        self.generate_imgs(modified_json, current_iteration, is_interrupted)
        self.first_run = False

    def generate_imgs(self, modified_json, current_iteration, is_interrupted) -> None:
        """Generate images using the ComfyConnector."""
        if self.comfy_connector is not None:
            self.comfy_connector.generate_images(
                modified_json, current_iteration, is_interrupted
            )

    def prepare_input(self) -> Optional[str]:
        """
        Prepare input directories and cache paths for workflow processing.

        Handles different input scenarios:
        - Directory paths without extensions (transfer all images)
        - Paths with "#" patterns (sequence files)
        - Single image files
        - Frame range processing
        """
        cache_path = None
        for i in self.input_dirs:
            cache_dir = []
            for key, path in i.items():
                cache_path = os.path.join(local_comfy_input, key)
                update_cache(cache_path)
                cache_dir.append(cache_path)
                self.cache_dirs.append(cache_path)

                if self.frame_range is None:
                    if not has_extension(path):
                        transfer_imgs_from_path(im_path=path, temp_dir=cache_path)
                        start_frame = get_first_frame(cache_path)
                        modify_start_frame(self.json_data, start_frame)
                    elif "#" in path:
                        copy_matching_files(path, cache_path)
                        start_frame = get_first_frame(cache_path)
                        modify_start_frame(self.json_data, start_frame)
                    else:
                        transfer_single_img(path, cache_path)
                else:
                    start_frame_str, end_frame_str = self.frame_range.split("-")
                    start_frame = int(start_frame_str)
                    end_frame = int(end_frame_str)
                    modify_start_frame(self.json_data, start_frame)

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
        """
        Execute the workflow with the configured parameters.

        Handles path extraction, cache preparation, batch processing,
        and progress tracking throughout the execution process.
        """
        self.check_duplicate_params()

        publishing_script = json_publish_script(self.json_data)
        if not publishing_script:
            self.input_dirs = extract_paths(self.str_args)
            if "#" not in self.input_dirs:
                clean_input_dirs(self.input_dirs)
            self.str_args = remove_extracted_paths(self.str_args, self.input_dirs)
            modify_dnloader(self.json_data, True)

        self.modify_json_with_params()
        cache_path = self.prepare_input()

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
                    if is_interrupted:
                        if is_interrupted():
                            self.interrupt()
                            break
                    current_iteration += 1
                    in_args = {}
                    for file in files:
                        node_name = get_folder_name(file)
                        in_args[node_name] = file
                    self.json_data = update_values(self.json_data, in_args)

                    if first_loop:
                        modify_fileout_folder_bool(self.json_data, True)
                        first_loop = False
                    else:
                        modify_fileout_folder_bool(self.json_data, False)

                    if current_iteration != total_iterations:
                        if not publishing_script:
                            json_data_copy = copy.deepcopy(self.json_data)
                            modified_json = remove_publisher(json_data_copy)
                        else:
                            modified_json = self.json_data
                    else:
                        modified_json = self.json_data

                    self.run_api(
                        modified_json,
                        current_iteration,
                        total_iterations,
                        is_interrupted,
                    )

            for cache in self.cache_dirs:
                shutil.rmtree(cache)
        else:
            current_iteration = 0
            total_iterations = 1
            self.run_api(
                self.json_data, current_iteration, total_iterations, is_interrupted
            )

        self.kill_api()
        kill_comfy_instances()

        self.progress = 100
        if self.progress_signal:
            self.progress_signal.emit(self.progress)

    def kill_api(self):
        """Kill the ComfyConnector API if it exists."""
        if self.comfy_connector is not None:
            self.comfy_connector.kill_api()

    def interrupt(self):
        """Handle workflow interruption by stopping API connections and cleaning up processes."""
        self._is_interrupted.set()
        try:
            self.kill_api()
            kill_comfy_instances()
        except Exception:
            pass
