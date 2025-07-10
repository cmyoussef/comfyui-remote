import os, shutil
import cv2
import numpy as np
from pathlib import Path
import re

### Cache Utils ###


def update_cache(cache_dir):
    if (
        os.path.isdir(cache_dir) == False
    ):  # if ADG_Matting cache folder does not exist, create
        Path(cache_dir).mkdir(parents=True, exist_ok=True)

    if os.listdir(
        cache_dir
    ):  # if there are any folders/files inside of ADG_Matting cache folder, clear all
        for filename in os.listdir(cache_dir):
            file_path = os.path.join(cache_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print("Failed to delete %s. Reason: %s" % (file_path, e))


def transfer_imgs_from_path(im_path, temp_dir):
    imgs = []
    if os.listdir(im_path):  # if there are any files in the user input folder
        for i in os.listdir(im_path):
            file_name, file_extension = os.path.splitext(i)
            if file_extension in {
                ".exr",
                ".png",
                ".jpg",
                ".jpeg",
                ".EXR",
                ".PNG",
                ".JPG",
                ".JPEG",
            }:
                imgs.append(i)
    else:
        raise Exception("No files found inside input path")
    for i in imgs:
        shutil.copy(im_path + "/" + i, temp_dir)


def transfer_imgs_from_list(im_list, temp_dir):
    imgs = []
    if im_list:
        for i in im_list:
            print(f"i={i}")
            img_name = os.path.basename(i)
            dir_path = os.path.dirname(i)

            file_name, file_extension = os.path.splitext(img_name)

            if file_extension in {
                ".exr",
                ".png",
                ".jpg",
                ".jpeg",
                ".EXR",
                ".PNG",
                ".JPG",
                ".JPEG",
            }:
                imgs.append(i)
    else:
        raise Exception("No files found in list")

    if imgs:
        for i in imgs:
            shutil.copy(i, temp_dir)
    else:
        raise Exception("No images found inside input path")


def transfer_single_img(img_path, temp_dir):
    imgs = []
    img_name = os.path.basename(img_path)
    dir_path = os.path.dirname(img_path)

    file_name, file_extension = os.path.splitext(img_name)

    if file_extension in {
        ".exr",
        ".png",
        ".jpg",
        ".jpeg",
        ".EXR",
        ".PNG",
        ".JPG",
        ".JPEG",
    }:
        imgs.append(img_name)

    for i in imgs:
        shutil.copy(dir_path + "/" + i, temp_dir)


def get_file_paths(cache_dir):
    """Walk through a directory and return sorted list of file paths."""
    file_paths = []
    for dirpath, _, filenames in os.walk(cache_dir):
        file_paths.extend(
            [os.path.join(dirpath, filename) for filename in sorted(filenames)]
        )
    return file_paths


def extend_list_to_length(file_list, length):
    """Extend a list to a specified length by repeating the last element."""
    return file_list + [file_list[-1]] * (length - len(file_list))


def iterate_through_files(cache_dirs):
    """Iterate through files in multiple directories, extending shorter lists."""
    # Collect file paths for each directory in cache_dirs
    files_list = [get_file_paths(cache_dir) for cache_dir in cache_dirs]
    # Determine the maximum length of the lists
    if not files_list:
        raise Exception("No input images found")
    max_length = max(len(files) for files in files_list)
    # Extend all lists to match the maximum length
    extended_files_list = [
        extend_list_to_length(files, max_length) for files in files_list
    ]
    # Now iterate through the extended lists simultaneously
    for files in zip(*extended_files_list):
        yield files


def get_folder_name(file_path):
    # Split the file path into parts
    parts = file_path.split(os.sep)

    # Ensure there are enough parts to get the second-to-last folder
    if len(parts) >= 2:
        return parts[-2]
    else:
        return None  # or you could return an empty string or another placeholder


def clean_input_dirs(input_dirs):
    """removes filenames leaving just the directory path"""
    # Pattern to match filenames ending specifically with ".####" or "_####"
    pattern = r"(.*[\\/])[^\\/]*[._]####(?:\.[^.]+)?$"

    # Iterate over each dictionary in the list
    for item in input_dirs:
        # Iterate over each key-value pair in the dictionary
        for key, path in item.items():
            # Check if path matches the pattern and extract the folder path if it does
            match = re.match(pattern, path)
            if match:
                # Update the path in the dictionary to just the folder path
                item[key] = match.group(1).rstrip("/")


def get_first_frame(folder_path):
    """
    Scans a folder for files with frame numbers in their names and returns the first frame number.

    Args:
        folder_path (str): Path to the folder containing the image sequence.

    Returns:
        int: The first frame number if found, or None if no frame numbers are present.
    """
    if not os.path.isdir(folder_path):
        raise ValueError(f"The provided path '{folder_path}' is not a valid directory.")

    # Regular expression to capture frame numbers in filenames
    frame_pattern = re.compile(r"(\d+)(?=\.\w+$)")

    frame_numbers = []

    # Scan through the files in the folder
    for file_name in os.listdir(folder_path):
        match = frame_pattern.search(file_name)
        if match:
            frame_numbers.append(int(match.group(0)))

    # Return the smallest frame number, or None if no valid frames found
    return min(frame_numbers) if frame_numbers else None


def copy_matching_files(input_path, cache_dir):
    """
    Copies files matching a pattern with frame numbers from the input directory to a cache directory.

    Args:
        input_path (str): The input path with "#" as a placeholder for frame numbers.
        cache_dir (str): The target directory where matching files will be copied.

    Raises:
        ValueError: If input_path doesn't contain "#" or the cache directory is invalid.
    """
    # Validate the input path for a frame placeholder
    if "#" not in input_path:
        raise ValueError(
            "The input path must contain '#' as a placeholder for frame numbers."
        )

    # Identify the base name (before the '#' placeholders)
    base_dir = os.path.dirname(input_path)
    base_name = os.path.basename(input_path).split("#")[0]

    # Ensure the cache directory exists
    os.makedirs(cache_dir, exist_ok=True)

    # Iterate through files in the base directory and find matches
    for file_name in os.listdir(base_dir):
        if file_name.startswith(base_name) and file_name.endswith(
            os.path.splitext(input_path)[1]
        ):
            src_path = os.path.join(base_dir, file_name)
            dest_path = os.path.join(cache_dir, file_name)
            shutil.copy(src_path, dest_path)
            print(f"Copied: {src_path} -> {dest_path}")
