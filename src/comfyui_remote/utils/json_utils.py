import os
import json
import random
from typing import Any, List

def load_json_data(json_file: str) -> dict:
    """
    Load JSON file.

    Args:
        json_file (str): The path to the JSON file.

    Returns:
        dict: The loaded JSON data.

    Raises:
        ValueError: If there is an error reading the JSON file.
    """
    try:
        with open(json_file, 'r') as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise ValueError(f"Error reading JSON file: {e}")

def modify_json_prompt(json_data: dict, new_pos_text: str, new_neg_text: str) -> dict:
    """
    Finds the positive and negative node parameters and updates the prompt to the user-specified prompt.

    Args:
        json_data (dict): The JSON data to be modified.
        new_pos_text (str): The new positive prompt text.
        new_neg_text (str): The new negative prompt text.

    Returns:
        dict: The modified JSON data.

    Raises:
        ValueError: If 'Positive' or 'Negative' title not found in any parameter.
    """
    # Flag to track if modification was made
    modified_pos = modified_neg = False
    # Iterate over each key-value pair in the dictionary
    for key, value in json_data.items():
        # Check if the current item contains the 'inputs' key and if the 'text' matches the search text
        if value["_meta"]["title"] == "CLIP Text Encode (Positive)":
            # Modify the positive 'text' parameter
            value['inputs']['text'] = new_pos_text
            modified_pos = True
        if value["_meta"]["title"] == "CLIP Text Encode (Negative)":
            # Modify the negative 'text' parameter
            value['inputs']['text'] = new_neg_text
            modified_neg = True
    # If no modification was made, raise an error
    if not modified_pos or not modified_neg:
        raise ValueError("'Positive' or 'Negative' title not found in any parameter. Please make sure to use the correct pre-set JSON template.")
    # Convert the dictionary back to a JSON string
    return json_data

        
def modify_syndata_input(json_data: dict, new_rgb_input: str, new_depth_input: str, new_mask_input: str) -> dict:
    # Flag to track if modification was made
    modified_rgb = modified_depth = modified_mask = False

    # Iterate over each key-value pair in the dictionary
    for key, value in json_data.items():
        # Check if the current item contains the 'inputs' key and if the 'text' matches the search text
        if value["_meta"]["title"] == "Load Image RGB":
            # Modify the 'image' parameter
            value['inputs']['image'] = new_rgb_input
            modified_rgb = True
        if value["_meta"]["title"] == "Load Image Depth":
            # Modify the 'image' parameter
            value['inputs']['image'] = new_depth_input
            modified_depth = True
        if value["_meta"]["title"] == "Load Image Mask":
            # Modify the 'image' parameter
            value['inputs']['image'] = new_mask_input
            modified_mask = True
        if value["class_type"] in ["KSampler", "ImpactWildcardEncode"]:
            value['inputs']['seed'] = random.randint(1, 2**64)
    # If no modification was made, raise an error
    if not modified_rgb or not modified_depth:
        raise ValueError("'Load Image RGB' or 'Load Image Depth' title not found in any parameter. Please make sure to use the correct pre-set JSON template.")
    if not modified_mask:
        raise ValueError("'Load Image Mask' title not found. Please make sure to use the correct pre-set JSON template.")

    # Convert the dictionary back to a JSON string
    return json_data

def is_input_dir(json_data: dict) -> bool:
    # Track if input node takes a directory as input
    return any(
        isinstance(value, dict) and value.get("class_type") == "VHS_LoadImagesPath"
        for value in json_data.values()
    )

def has_input_node(json_data: dict) -> bool:
    # Track if json file has an input node
    """Check if JSON has an input node."""
    return any(
        isinstance(value, dict) and value.get("class_type") in ["VHS_LoadImagesPath", "LoadImage"]
        for value in json_data.values()
    )

def search_params(json_data: dict, node_class: str) -> List[str]:
    """Generalized search for int, float, and str parameters.

    takes as input: json data and string of class_type: dnInteger, dnString dnFloat.

    returns: full name of node (title)"""
    
    param_list = []
    for key, value in json_data.items():
        if isinstance(value, dict) and "class_type" in value:
            if value["class_type"] == node_class:
                class_type = value["_meta"]["title"]
                param_list.append(class_type)
    return param_list

def update_values(json_data: dict, returned_args: dict, value_key: str) -> dict:
    """Generalized update function for int, float, and str parameters.

    takes as input: json data, new param values, value replacement key (from json file)"""

    title_to_key = {value['_meta']['title']: key for key, value in json_data.items() if '_meta' in value}
    for arg_key, arg_value in returned_args.items():
        key_to_update = title_to_key[arg_key]
        json_data[key_to_update]['inputs'][value_key] = arg_value
        #print(f"Updated {arg_key} to {arg_value} in key {key_to_update}")

    return json_data

def modify_json_input_dir(json_data: dict, input_ims: str) -> dict:
    """
    Modifies the input directory parameter.

    Args:
        json_data (dict): The JSON data to be modified.
        input_dir (str): The new input directory or images.

    Returns:
        dict: The modified JSON data.

    Raises:
        NotADirectoryError: If the provided input_dir is not a directory.
        ValueError: If LoadImage parameter is not found in the JSON data.
    """
    
    # Flag to track if modification was made
    modified = False
    for key, value in json_data.items():
        if isinstance(value, dict) and "class_type" in value:
            if value["class_type"] == "VHS_LoadImagesPath":
                # Check if input is a directory
                if not os.path.isdir(input_ims):
                    raise NotADirectoryError(input_ims)
                value["inputs"]["directory"] = input_ims
                modified = True
            if value["class_type"] == "LoadImage":
                value["inputs"]["image"] = input_ims
                modified = True
    #If no modification was made, raise an error
    if not modified:
        raise ValueError("Neither LoadImage nor VHS_LoadImagesPath parameter found. Please make sure to use the correct pre-set JSON template.")
    return json_data

def get_dnfileout_version(data):
    # Iterate over all keys in the JSON data
    for key, value in data.items():
        # Check if the class_type is 'dnFileOut'
        if value.get('class_type') == 'dnFileOut':
            # Return the version if it exists
            return value.get('inputs', {}).get('version')
    # If no 'dnFileOut' class_type is found, return None
    return None

def _modify_json_param(json_data: dict, class_type: str, param_name: str, new_value: Any) -> dict:
    """
    Helper function to modify a JSON parameter.

    Args:
        json_data (dict): The JSON data to be modified.
        class_type (str): The class type to look for.
        param_name (str): The parameter name to modify.
        new_value (Any): The new value for the parameter.

    Returns:
        dict: The modified JSON data.

    Raises:
        ValueError: If the parameter is not found in the JSON data.
    """
    modified = False
    for key, value in json_data.items():
        # Check if the value is a dictionary and contains the required keys
        if isinstance(value, dict) and value.get("class_type") == class_type:
            if "inputs" in value and isinstance(value["inputs"], dict):
                value["inputs"][param_name] = new_value
                modified = True

    if not modified:
        raise ValueError("Parameter not found. Please make sure to use the correct pre-set JSON template.")
    
    return json_data

# Parameter Modification Functions
def modify_json_steps_param(json_data: dict, steps: int) -> dict:
    """
    Modifies the steps parameter 
    """
    return _modify_json_param(json_data, "KSampler", "steps", steps)

def modify_json_cfg_param(json_data: dict, cfg: int) -> dict:
    """
    Modifies the cfg parameter 
    """
    return _modify_json_param(json_data, "KSampler", "cfg", cfg)

def modify_json_denoise_param(json_data: dict, denoise: float) -> dict:
    """
    Modifies the denoise parameter 
    """
    return _modify_json_param(json_data, "KSampler", "denoise", denoise)

def modify_json_seed_param(json_data: dict, seed: int) -> dict:
    """
    Modifies the seed parameter 
    """
    return _modify_json_param(json_data, "KSampler", "seed", seed)

def modify_json_controlnet_param(json_data: dict, controlnet: float) -> dict:
    """
    Modifies the controlnet strength parameter 
    """
    return _modify_json_param(json_data, "ControlNetApply", "strength", controlnet)

#def modify_json_output_param(json_data: dict, filename: str) -> dict:
    #"""
    #Modifies the controlnet strength parameter 
    #"""
    #return _modify_json_param(json_data, "SaveImage", "filename_prefix", filename)