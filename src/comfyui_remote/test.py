import os
import subprocess
import ast
from pathlib import Path
import re

def get_frameRange(folder_path):
    # List all files in the folder
    files = os.listdir(folder_path)
    
    # Extract numeric parts from filenames
    numbers = []
    for file in files:
        match = re.search(r'(\d+)(?!.*\d)', file)
        if match:
            numbers.append(int(match.group(1)))

    
    # If no numbers were found, return "no frame range"
    if not numbers:
        return False #"no frame range or missing frames -- rendering all images in directory""
    
    # Sort the numbers
    numbers.sort()
    
    # Check if numbers form a consecutive sequence
    for i in range(1, len(numbers)):
        if numbers[i] != numbers[i-1] + 1:
            return False #"no frame range or missing frames -- rendering all images in directory"
    
    # Return the frame range
    return f"{numbers[0]}-{numbers[-1]}"

framerange = get_frameRange("/hosts/glasgow/user_data/comfyui/output/046")
print(f'framerange={framerange}')