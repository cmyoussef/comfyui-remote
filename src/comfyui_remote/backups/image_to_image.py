import os
import json
import argparse
from executors.api_executor import ComfyConnector
from utils.common_utils import (
    modify_json_prompt, modify_json_input_dir, modify_json_steps_param,
    modify_json_cfg_param, modify_json_denoise_param, modify_json_seed_param, modify_json_controlnet_param,
    modify_json_filename_param, load_json_data, set_output_path
)


class ImageToImageConverter:
    def __init__(self, json_file, input_dir, output_filename, positive_prompt, negative_prompt, steps, cfg, denoise, seed, controlnet):
        self.json_file = json_file
        self.input_dir = input_dir
        self.output_filename = output_filename
        self.positive_prompt = positive_prompt
        self.negative_prompt = negative_prompt
        self.steps = steps
        self.cfg = cfg
        self.denoise = denoise
        self.seed = seed
        self.controlnet_strength = controlnet
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
        # modify the steps parameter
        self.json_data = modify_json_steps_param(self.json_data, self.steps)
        # modify the cfg parameter
        self.json_data = modify_json_cfg_param(self.json_data, self.cfg)
        # modify the denoise parameter
        self.json_data = modify_json_denoise_param(self.json_data, self.denoise)
        # modify the seed parameter
        self.json_data = modify_json_seed_param(self.json_data, self.seed)
        # modify the json control net strength param
        self.json_data = modify_json_controlnet_param(self.json_data, self.controlnet_strength)
        # modify input directory parameter
        self.json_data = modify_json_input_dir(self.json_data, self.input_dir)
        print("Input directory parameter updated.")

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
    parser.add_argument('--output_filename', type=str, default=set_output_path('Img_to_Img'), help='Path to input directory')
    parser.add_argument('--positive_prompt', type=str, default='', required=True, help='Your desired image prompt')
    parser.add_argument('--negative_prompt', type=str, default='', required=True, help='Text prompt to avoid in your image')
    parser.add_argument('--steps', type=int, default=20, help='The number of iterations the diffusion model will execute')
    parser.add_argument('--cfg', type=int, default=5, help='The "classifier-free guidance" parameter adjusts the strength of the guidance')
    parser.add_argument('--denoise', type=float, default=1.0, help='Amount of noise reduction applied during the generation process')
    parser.add_argument('--seed', type=int, default=965523139411390, help='The initial value for the random number generator')
    parser.add_argument('--controlnet_strength', type=float, default=0.8, help='Strength of balance between adherence to control signals and creative freedom')

    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()
    
    try:
       converter = ImageToImageConverter(
            json_file=args.json_file,
            input_dir=args.input_dir,
            output_filename=args.output_filename,
            positive_prompt = args.positive_prompt,
            negative_prompt=args.negative_prompt,
            steps=args.steps,
            cfg=args.cfg,
            denoise=args.denoise,
            seed=args.seed,
            controlnet=args.controlnet_strength
       )
       converter.load_and_modify_json()
       converter.execute_api()

    except ValueError as e:
        print(f"An error occured: {e}")
