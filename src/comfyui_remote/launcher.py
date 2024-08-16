import os
import json
import argparse
import subprocess
from executors.api_executor import ComfyConnector
from config.settings_config import local_comfy_input, local_comfy_outputs
from utils.json_utils import (
    modify_json_input_dir, modify_json_output_param, load_json_data, is_input_dir, has_input_node,
    search_params, update_values
)
from utils.cache_utils import update_cache, transfer_imgs_from_path, transfer_imgs_from_list, transfer_single_img
from utils.common_utils import (
    create_sequential_folder, kill_comfy_instances, has_frame_range, desired_frame_range, get_filenames_in_range,
    has_extension
)

class ExecuteWorkflow:
    def __init__(self, json_file: str, input_dir: str, batch_size: int):
        self.json_file = json_file
        self.input_dir = input_dir
        self.batch_size = batch_size
        self.json_data = load_json_data(self.json_file)
        self.int_args = {}
        self.float_args = {}
        self.str_args = {}
        self.comfy_connector = None

    def request_param_inputs(self) -> None:
        params = {
            'int': search_params(self.json_data, 'int'),
            'float': search_params(self.json_data, 'float'),
            'str': search_params(self.json_data, 'str')
        }

        for param_type, param_list in params.items():
            for param in param_list:
                value = input(f'Please enter value for {param} ({param_type}):')
                if param_type == 'int':
                    self.int_args[param] = value
                elif param_type == 'float':
                    self.float_args[param] = value
                elif param_type == 'str':
                    self.str_args[param] = value

    def modify_json_with_params(self, img_in: str, temp_output: str) -> None:
        """
        Modify JSON file with user prompts.

        Returns:
            dict: Modified JSON content.
        """
        if self.input_dir:
            # modify input directory parameter
            self.json_data = modify_json_input_dir(self.json_data, img_in)
        if self.int_args:
            self.json_data = update_values(self.json_data, self.int_args, 'int', 'value')
        if self.float_args:
            self.json_data = update_values(self.json_data, self.float_args, 'float', 'value')
        if self.str_args:
            self.json_data = update_values(self.json_data, self.str_args, 'str', 'string')
        # Update the output filename param
        self.json_data = modify_json_output_param(self.json_data, temp_output) # Set an output name

    def run_api(self) -> None:
        if not self.json_data:
            raise ValueError("JSON data is not loaded or modified")
        self.comfy_connector = ComfyConnector(self.json_data)
        self.generate_imgs()

    def generate_imgs(self) -> None:
        self.comfy_connector.generate_images(self.json_data)

    def prepare_input(self) -> None:
        # Update Cache folder
        update_cache(local_comfy_input)
        if not has_extension(self.input_dir):
            # Check for frame range in input dir, if found, have user input desired frame range to process
            is_sequence = has_frame_range(self.input_dir)
            if is_sequence:
                start, end = desired_frame_range()
                input_filenames = get_filenames_in_range(self.input_dir, start, end)
                #transfer (and convert if EXR) frame range inputs to temp dir
                transfer_imgs_from_list(im_list=input_filenames, temp_dir=local_comfy_input)
            else:
                # transfer all imgs in input dir (and convert if EXR)
                transfer_imgs_from_path(im_path=self.input_dir, temp_dir=local_comfy_input)
        else:
            transfer_single_img(self.input_dir, local_comfy_input)
        # update new input from temp dir
        self.input_dir=local_comfy_input

    def execute(self):
        # Check if JSON has an input node, make sure user added input arg
        if has_input_node(self.json_data) and not self.input_dir:
            raise ValueError("Input directory is required for this JSON workflow. Please use --input_dir arg.")

        self.prepare_input()
        # update temporary output path
        temp_output_path = os.path.join(create_sequential_folder(local_comfy_outputs), "ComfyUI_output")

        # request user args
        self.request_param_inputs()

        # Check if the input node takes in a directory as input
        input_node_type_dir = is_input_dir(self.json_data)

        img_files = sorted(os.listdir(self.input_dir)) if not input_node_type_dir else [self.input_dir]

        for batch_num in range(1, self.batch_size + 1):
            for img_in in img_files:
                self.modify_json_with_params(img_in, f"{temp_output_path}{batch_num}")
                self.run_api()

        self.comfy_connector.kill_api()
        kill_comfy_instances()

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description='ComfyUI Serverless Commands')
    parser.add_argument('--json_file', type=str, default='', required=True, help='Path and name to JSON dev file')
    parser.add_argument('--input_dir', type=str, default='', help='Path to input directory')
    parser.add_argument('--batch_size', type=int, default=1, help='The number of times to execute the entire workflow. default=1.')
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()

    try:
       executor = ExecuteWorkflow(
            json_file=args.json_file,
            input_dir=args.input_dir,
            batch_size=args.batch_size
       )
       executor.execute()

    except ValueError as e:
        print("An error occured={}".format(e))