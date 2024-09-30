import os
import json
import argparse
from executors.api_executor import ComfyConnector
from utils.common_utils import modify_json_filename_param, load_json_data, set_output_path, modify_syndata_input

class ExecuteWorkflow:
    def __init__(self, json_file, input_rgb_dir, input_depth_dir, input_mask_dir, output_filename):
        self.json_file = json_file
        self.input_rgb_dir = input_rgb_dir
        self.input_depth_dir = input_depth_dir
        self.input_mask_dir = input_mask_dir
        self.output_filename = output_filename
        self.json_data = None

    def run_syndata(self, img_in_rgb, img_in_depth, img_in_mask):
        """
        Load JSON file and modify with user prompts.

        Returns:
            dict: Modified JSON content.
        """

        # The json_data is a JSON object that contains a prompt that will be used
        self.json_data = load_json_data(self.json_file)
        print("JSON File loaded...")
        # modify input directory parameter
        self.json_data = modify_syndata_input(self.json_data, img_in_rgb, img_in_depth, img_in_mask)
        print("Input directory parameter updated.")
        # Update the output filename param
        self.json_data = modify_json_filename_param(self.json_data, self.output_filename)
        print("Output filepath updated.")

        if self.json_data is None:
            raise ValueError("JSON data is not loaded or modified")
        self.comfy_connector = ComfyConnector(self.json_data)
        self.comfy_connector.kill_api()

    def iterate_and_run(self):
        # List all files in the directory
        rgb_files = sorted(os.listdir(self.input_rgb_dir))
        depth_files = sorted(os.listdir(self.input_depth_dir))
        mask_files = sorted(os.listdir(self.input_mask_dir))

        # Iterate through the files in the directories
        for rgb_file, depth_file, mask_file in zip(rgb_files, depth_files, mask_files):
            img_in_rgb = os.path.join(self.input_rgb_dir, rgb_file)
            img_in_depth = os.path.join(self.input_depth_dir, depth_file)
            img_in_mask = os.path.join(self.input_mask_dir, mask_file)

            #call run_syndata with each image
            self.run_syndata(img_in_rgb, img_in_depth, img_in_mask)
            

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description='Text to Image commands')
    parser.add_argument('--json_file', type=str, default='', required=True, help='Path and name to JSON dev file')
    parser.add_argument('--input_rgb_dir', type=str, default='', required=True, help='Path to input RGB directory')
    parser.add_argument('--input_depth_dir', type=str, default='', required=True, help='Path to input Depth directory')
    parser.add_argument('--input_mask_dir', type=str, default='', required=True, help='Path to input Mask directory')
    parser.add_argument('--output_filename', type=str, default=set_output_path('Syndata_Outputs'), help='output directory/filename. Example: test_output/filename (do not include extension such as .png)')
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()

    try:
       executor = ExecuteWorkflow(
            json_file=args.json_file,
            input_rgb_dir=args.input_rgb_dir,
            input_depth_dir=args.input_depth_dir,
            input_mask_dir=args.input_mask_dir,
            output_filename=args.output_filename
       )
       executor.iterate_and_run()

    except ValueError as e:
        print(f"An error occured: {e}")