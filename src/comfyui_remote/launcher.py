import os, shutil
import json
import tyro
import subprocess
import copy
from typing import Optional
from executors.api_executor import ComfyConnector
from config.settings_config import local_comfy_path, local_comfy_input, local_comfy_outputs
from utils.json_utils import (
    modify_json_input_dir, load_json_data, has_input_node,
    search_params, update_values, get_dnfileout_version, is_input_dir, modify_fileout_folder_bool, remove_publisher
)
from utils.cache_utils import (
    update_cache, transfer_imgs_from_path, transfer_imgs_from_list, transfer_single_img, get_file_paths, extend_list_to_length,
    iterate_through_files, get_folder_name
)
from utils.common_utils import (
    kill_comfy_instances, has_frame_range, desired_frame_range, get_filenames_in_range,
    has_extension, extract_paths, remove_extracted_paths
)

class ExecuteWorkflow:
    def __init__(self, json_file: str, batch_size: int = 1, frame_range: Optional[str] = None, int_args: Optional[str] = None, float_args: Optional[str] = None, str_args: Optional[str] = None):
        self.json_file = json_file
        self.batch_size = batch_size
        self.frame_range = frame_range
        self.input_dirs = []
        self.cache_dirs = []
        self.first_run = True

        self.json_data = load_json_data(self.json_file)
        self.comfyui_version = get_dnfileout_version(self.json_data)

        # Load optional arguments with default as empty dict
        self.int_args = self.load_json_safe(int_args, "integer") if int_args else {}
        self.float_args = self.load_json_safe(float_args, "float") if float_args else {}
        self.str_args = self.load_json_safe(str_args, "string") if str_args else {}

        self.params = {
            'int': search_params(self.json_data, 'dnInteger'),
            'float': search_params(self.json_data, 'dnFloat'),
            'str': search_params(self.json_data, 'dnString')
        }
        self.comfy_connector = None

    def load_json_safe(self, arg: Optional[str], arg_type: str):
        """Safely loads JSON and provides a custom error message."""
        try:
            return json.loads(arg) if arg else {}
        except json.JSONDecodeError:
            raise ValueError(f"Error in {arg_type} argument: Please ensure the string arguments are properly formatted with quotation marks.")

    def request_param_inputs(self, param, param_type) -> None:
            while True:
                value = input(f'Please enter value for {param} ({param_type}): ')
                if value.strip():  # Check if value is not empty or just spaces
                    if param_type == 'int':
                        self.int_args[param] = value
                    elif param_type == 'float':
                        self.float_args[param] = value
                    elif param_type == 'str':
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

    def display_command(self):
        command = f"dncomfyui -r --json_file {self.json_file} --batch_size {self.batch_size}"
        
        if self.frame_range:
            command += f" --frame_range {self.frame_range}"
        if self.int_args:
            command += f" --int_args '{json.dumps(self.int_args)}'"
        if self.str_args:
            # If input_dirs exists, merge its 'inputPath' with str_args
            if self.input_dirs:
                self.str_args['inputPath'] = self.input_dirs[0]['inputPath']  # Add inputPath to str_args
            command += f" --str_args '{json.dumps(self.str_args)}'"
        if self.float_args:
            command += f" --float_args '{json.dumps(self.float_args)}'"
        
        print(command)

    def run_api(self, modified_json) -> None:
        if not modified_json:
            raise ValueError("JSON data is not loaded or modified")
        print("comfyui_version={}".format(self.comfyui_version))
        self.comfy_connector = ComfyConnector(modified_json, self.comfyui_version) # First image is generated here as a "test image"

        # Skip generate_imgs() the first time
        if not self.first_run:
            self.generate_imgs(modified_json)

        #after first run, set first_run to False
        self.first_run = False

    def generate_imgs(self, modified_json) -> None:
        self.comfy_connector.generate_images(modified_json)

    def prepare_input(self) -> None:
        # Process each input directory
        for i in self.input_dirs:
            cache_dir = []  # Reset cache dirs for each input
            for key, path in i.items():
                # Update Cache folder
                cache_path = os.path.join(local_comfy_input, key)
                update_cache(cache_path)
                cache_dir.append(cache_path)
                self.cache_dirs.append(cache_path)

                if self.frame_range == None:
                    if not has_extension(path):
                        # Check if directory contains a sequence of frames
                        is_sequence = has_frame_range(path)

                        if is_sequence:
                            # Handle sequence frame range
                            start, end = desired_frame_range(key)
                            input_filenames = get_filenames_in_range(path, start, end)
                            transfer_imgs_from_list(im_list=input_filenames, temp_dir=cache_path)
                        else:
                            # Transfer all images from the directory
                            transfer_imgs_from_path(im_path=path, temp_dir=cache_path)
                    else:
                        # Handle single image path
                        transfer_single_img(path, cache_path)
                else:
                    start_frame, end_frame = self.frame_range.split('-')
                    start_frame = int(start_frame)
                    end_frame = int(end_frame)
                    # Ensure the start frame is less than or equal to the end frame
                    if start_frame > end_frame:
                        print("Error: Start frame must be less than or equal to end frame.")
                        continue
                    input_filenames = get_filenames_in_range(path, start_frame, end_frame)
                    transfer_imgs_from_list(im_list=input_filenames, temp_dir=cache_path)
            return cache_path

    def execute(self):

        self.check_duplicate_params()


        # prompt user input if not specified in CLI
        for param_type, param_list in self.params.items():
            for param in param_list:
                if param not in self.int_args and param not in self.float_args and param not in self.str_args:
                    print(f"Parameter '{param}' not found in any argument lists.")
                    self.request_param_inputs(param, param_type)

        # extract any paths from str args
        self.input_dirs = extract_paths(self.str_args)
        # remove any input strings from str_args so that we have them seperated
        self.str_args = remove_extracted_paths(self.str_args, self.input_dirs)
        # update user args
        self.modify_json_with_params()

        # update cache dirs
        cache_path = self.prepare_input()

        first_loop = True

        # Check if the input node takes in a directory as input
        #input_node_type_dir = is_input_dir(self.json_data)

        if cache_path:
            total_iterations = sum(1 for _ in iterate_through_files(self.cache_dirs)) * self.batch_size
            current_iteration = 0
            for batch_num in range(1, self.batch_size + 1):
                for files in iterate_through_files(self.cache_dirs):
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
                        # Remove any dnPublisher nodes if its not the final iteration
                        json_data_copy = copy.deepcopy(self.json_data)
                        modified_json = remove_publisher(json_data_copy)
                    else:
                        modified_json = self.json_data

                    self.run_api(modified_json)
            for cache in self.cache_dirs:
                shutil.rmtree(cache)
        else:
            self.run_api(self.json_data)
        self.comfy_connector.kill_api()
        kill_comfy_instances()
        self.display_command()

if __name__ == '__main__':
    executor = tyro.cli(ExecuteWorkflow)
    executor.execute()

 