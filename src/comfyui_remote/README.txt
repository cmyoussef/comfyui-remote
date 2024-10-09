ComfyUIRemote
ComfyUIRemote is a tool for executing workflows in ComfyUI by specifying a JSON file that defines the workflow and its associated parameters.

Usage
To run the tool, use the following command in your terminal:
dncomfyui -r --json_file <path_to_json> --batch_size <batch_size>

Required Parameters:
--json_file: Path to the JSON file containing the workflow.
--batch_size: The number of times you want the workflow to be executed.
Optional Parameters:
--frame_range: The range of frames for input images (format: start-end). Example: --frame_range 0-10
--int_args: Dictionary containing any dnNode in ComfyUI that requires an integer input.
--float_args: Dictionary containing any dnNode in ComfyUI that requires a float input.
--str_args: Dictionary containing any dnNode in ComfyUI that requires a string input.
Format for --int_args, --float_args, and --str_args
To pass in arguments for the dnNode that require integers, floats, or strings, enter them in the form of a dictionary with the name of the dnNode and its value.

Example:
dncomfyui -r --json_file script_files/img_to_img/img2img_v018.json --batch_size 1 \
--frame_range 0-1 \
--int_args '{"Steps": 50, "Seed": 432432}' \
--str_args '{"PositivePrompt": "a cow wearing a hat", "NegativePrompt": "realistic", "inputPath": "/u/gdso/Pictures/syndata_test/imgs"}' \
--float_args '{"cnStrength": 0.8}'

Explanation:
--json_file: The workflow file in JSON format.
--batch_size: Executes the workflow once.
--frame_range: Specifies the frame range from 0 to 1.
--int_args: Passes integer arguments to the dnNode, such as setting Steps to 50 and Seed to 432432.
--str_args: Specifies string arguments like prompts.
--float_args: Provides float values like cnStrength set to 0.8.
