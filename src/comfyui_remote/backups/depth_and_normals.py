import os
import json
import argparse
from executors.api_executor import ComfyConnector
from utils.common_utils import modify_json_input_dir, modify_json_filename_param, load_json_data, set_output_path

class DepthNormalsConverter:
    def __init__(self, json_file, input_dir, output_filename):
        self.json_file = json_file
        self.input_dir = input_dir
        self.output_filename = output_filename
        self.json_data = None

    def load_and_modify_json(self):
        """
        Load JSON file and modify with user prompts.

        Returns:
            dict: Modified JSON content.
        """
        # The json_data is a JSON object that contains a prompt that will be used
        self.json_data = load_json_data(self.json_file)
        # modify input directory parameter
        self.json_data = modify_json_input_dir(self.json_data, self.input_dir)
        print("Input directory parameter updated.")
        # Update the output filename param
        self.json_data = modify_json_filename_param(self.json_data, self.output_filename)


    def execute_api(self):
        if self.json_data is None:
            raise ValueError("JSON data is not loaded or modified")
        comfy_connector = ComfyConnector(self.json_data)
        comfy_connector.kill_api()

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description='Text to Image commands')
    parser.add_argument('--json_file', type=str, default='', required=True, help='Path and name to JSON dev file')
    parser.add_argument('--input_dir', type=str, default='', required=True, help='Path to input directory')
    parser.add_argument('--output_filename', type=str, default=set_output_path('Depth_Normals'), help='Path to input directory')
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()

    try:
       converter = DepthNormalsConverter(
            json_file=args.json_file,
            input_dir=args.input_dir,
            output_filename=args.output_filename
       )
       converter.load_and_modify_json()
       converter.execute_api()

    except ValueError as e:
        print(f"An error occured: {e}")