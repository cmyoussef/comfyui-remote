import os
import json
import argparse
from utils.common_utils import (
    modify_json_prompt, modify_json_steps_param, modify_json_cfg_param, modify_json_filename_param,
    modify_json_denoise_param, modify_json_seed_param, load_json_data, set_output_path
)
from executors.api_executor import ComfyConnector


class TextToImageConverter:
    def __init__(self, json_file, output_filename, positive_prompt, negative_prompt, steps, cfg,
                denoise, seed):
        self.json_file = json_file
        self.output_filename = output_filename
        self.positive_prompt = positive_prompt
        self.negative_prompt = negative_prompt
        self.steps = steps
        self.cfg = cfg
        self.denoise = denoise
        self.seed = seed
        self.json_data = None

    def load_and_modify_json(self):
        """
        Load JSON file and modify with user prompts.

        Returns:
            dict: Modified JSON content.
        """
        # The json_data is a JSON object that contains a prompt that will be used
        self.json_data = load_json_data(self.json_file)
        # modify the default positive and negative prompt to the user specified prompts
        self.json_data = modify_json_prompt(self.json_data, self.positive_prompt, self.negative_prompt)
        print("Positive and negative prompt parameter updated.")
        # Update the output filename param
        self.json_data = modify_json_filename_param(self.json_data, self.output_filename)
        # modify the cfg parameter
        self.json_data = modify_json_cfg_param(self.json_data, self.cfg)
        # modify the denoise parameter
        self.json_data = modify_json_denoise_param(self.json_data, self.denoise)
        # modify the seed parameter
        self.json_data = modify_json_seed_param(self.json_data, self.seed)
        # modify the steps parameter
        self.json_data = modify_json_steps_param(self.json_data, self.steps)

    def execute_api(self):
        if self.json_data is None:
            raise ValueError("JSON data is not loaded or modified")
        comfy_connector = ComfyConnector(self.json_data)
        comfy_connector.kill_api()

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description='Text to Image commands')
    parser.add_argument('--json_file', type=str, default='', required=True, help='Path and name to JSON dev file')
    parser.add_argument('--output_filename', type=str, default=set_output_path('Txt_to_Img'), help='Path to input directory')
    parser.add_argument('--positive_prompt', type=str, default='', required=True, help='Your desired image prompt')
    parser.add_argument('--negative_prompt', type=str, default='', required=True, help='Text prompt to avoid in your image')
    parser.add_argument('--steps', type=int, default=20, help='The number of iterations the diffusion model will execute')
    parser.add_argument('--cfg', type=int, default=5, help='The "classifier-free guidance" parameter adjusts the strength of the guidance')
    parser.add_argument('--denoise', type=float, default=1.0, help='Amount of noise reduction applied during the generation process')
    parser.add_argument('--seed', type=int, default=232781511651730, help='The initial value for the random number generator')

    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()

    try:
       converter = TextToImageConverter(
            json_file=args.json_file,
            output_filename=args.output_filename,
            positive_prompt = args.positive_prompt,
            negative_prompt=args.negative_prompt,
            steps=args.steps,
            cfg=args.cfg,
            denoise=args.denoise,
            seed=args.seed
       )
       converter.load_and_modify_json()
       converter.execute_api()

    except ValueError as e:
        print(f"An error occured: {e}")