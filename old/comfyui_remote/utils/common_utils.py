import logging
import os
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"


def kill_comfy_instances():
    subprocess.run(
        "ps ux | grep python | grep cuda | grep gui.py | awk '{print $2}' | xargs kill",
        shell=True,
    )


def create_sequential_folder(base_path):
    # Ensure the base path exists
    if not os.path.exists(base_path):
        raise ValueError("The specified base path does not exist")

    # Find the next available folder name
    folder_number = 1
    while True:
        folder_name = f"{folder_number:03d}"
        folder_path = os.path.join(base_path, folder_name)
        if not os.path.exists(folder_path):
            break
        folder_number += 1

    # Create the new folder
    os.makedirs(folder_path)
    logger.info(f"Created folder: {folder_path}")
    return folder_path


def get_latest_folder(base_path):
    # List all items in the base directory
    folders = [
        f for f in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, f))
    ]

    # Filter out folders that don't match the pattern
    numeric_folders = [f for f in folders if f.isdigit()]

    if not numeric_folders:
        return None  # Return None if no matching folders are found

    # Convert folder names to integers and find the max (latest)
    latest_folder = max(numeric_folders, key=int)

    # Return the full path to the latest folder
    return os.path.join(base_path, latest_folder)


def get_filenames(path):
    if os.path.isfile(path):
        # If the path is a file, return the filename without the extension
        return os.path.splitext(os.path.basename(path))[0]
    elif os.path.isdir(path):
        # If the path is a directory, return a list of filenames in the directory without the extensions
        return [
            os.path.splitext(filename)[0]
            for filename in os.listdir(path)
            if os.path.isfile(os.path.join(path, filename))
        ]
    else:
        raise ValueError(f"The path {path} does not exist.")


def extract_paths(input_dict):
    paths = []
    for key, value in input_dict.items():
        if isinstance(value, str):
            path = Path(value)
            # Check if the path is absolute or exists relative to the current directory
            if path.is_absolute() or path.exists():
                paths.append({key: value})
    return paths


def remove_extracted_paths(input_dict, extracted_paths):
    for path_dict in extracted_paths:
        for key in path_dict:
            input_dict.pop(key, None)
    return input_dict


def has_frame_range(folder_path):
    # List all files in the folder
    files = os.listdir(folder_path)

    # Extract numeric parts from filenames
    numbers = []
    for file in files:
        match = re.search(r"(\d+)(?!.*\d)", file)
        if match:
            numbers.append(int(match.group(1)))

    # If no numbers were found, return "no frame range"
    if not numbers:
        return False  # "no frame range or missing frames -- rendering all images in directory""

    # Sort the numbers
    numbers.sort()

    # Check if numbers form a consecutive sequence
    for i in range(1, len(numbers)):
        if numbers[i] != numbers[i - 1] + 1:
            return False  # "no frame range or missing frames -- rendering all images in directory"

    # Return the frame range
    return True  # f"{numbers[0]}-{numbers[-1]}"


def get_filenames_in_range(directory, start, end):
    matching_filenames = []

    # Regular expression pattern to find a sequence of digits in the filename
    pattern = re.compile(r"(\d+)")

    for filename in os.listdir(directory):
        # Find all sequences of digits in the filename
        matches = pattern.findall(filename)

        if matches:
            # Convert all matches to integers and check if any match is within the range
            for match in matches:
                frame_number = int(match)
                if start <= frame_number <= end:
                    matching_filenames.append(os.path.join(directory, filename))
                    break  # Stop checking further once a valid frame number is found
    if not matching_filenames:
        raise Exception("Frame Range not found")
    else:
        return matching_filenames


def has_extension(filepath):
    # Extract the base name from the filepath
    filename = os.path.basename(filepath)
    # Split the filename and extension
    name, extension = os.path.splitext(filename)
    # Check if the extension is not empty
    return bool(extension)
