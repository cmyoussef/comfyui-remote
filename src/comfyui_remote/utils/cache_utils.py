import os, shutil
import cv2
import numpy as np
from pathlib import Path

### Cache Utils ###

def update_cache(cache_dir):

    if os.path.isdir(cache_dir) == False:  # if ADG_Matting cache folder does not exist, create
        Path(cache_dir).mkdir(parents=True, exist_ok=True)

    if os.listdir(cache_dir):  # if there are any folders/files inside of ADG_Matting cache folder, clear all
        for filename in os.listdir(cache_dir):
            file_path = os.path.join(cache_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print('Failed to delete %s. Reason: %s' % (file_path, e))

def transfer_imgs_from_path(im_path, temp_dir):
    cont = True
    if os.listdir(im_path):  # if there are any files in the user input folder
        for i in os.listdir(im_path):
            file_name, file_extension = os.path.splitext(i)

            if file_extension not in {'.exr', '.png', '.jpg', '.jpeg', '.EXR', '.PNG', '.JPG', '.JPEG'}:
                cont = False
                print(file_extension)
                raise Exception("Please make sure your files are either EXR's, PNG's, or JPEG's")

            if cont == True and file_extension == '.exr':
                full_im_path = os.path.join(im_path, i)
                img = cv2.imread(full_im_path, -1)
                img = img * 65535
                img[img > 65535] = 65535
                img = np.uint16(img)

                png_name = i.replace('.exr', '.png')
                full_output_path = os.path.join(temp_dir, png_name)
                cv2.imwrite(full_output_path, img)

            elif cont == True and file_extension != '.exr':
                shutil.copy(im_path + '/' + i, temp_dir)
    else:
        raise Exception("No files found inside input path")

def transfer_imgs_from_list(im_list, temp_dir):
    cont = True
    if im_list:
        for i in im_list:
            img_name = os.path.basename(i)
            dir_path = os.path.dirname(i)

            file_name, file_extension = os.path.splitext(img_name)
            
            if file_extension not in {'.exr', '.png', '.jpg', '.jpeg', '.EXR', '.PNG', '.JPG', '.JPEG'}:
                cont = False
                print(file_extension)
                raise Exception("Please make sure your files are either EXR's, PNG's, or JPEG's")

            if cont == True and file_extension == '.exr':
                img = cv2.imread(i, -1)
                img = img * 65535
                img[img > 65535] = 65535
                img = np.uint16(img)
                
                png_name = img_name.replace('.exr', '.png')
                full_output_path = os.path.join(temp_dir, png_name)
                cv2.imwrite(full_output_path, img)

            elif cont == True and file_extension != '.exr':
                shutil.copy(dir_path + '/' + img_name, temp_dir)
    else:
        raise Exception("No files found in list")

def transfer_single_img(img_path, temp_dir):
    cont = True
    img_name = os.path.basename(img_path)
    dir_path = os.path.dirname(img_path)

    file_name, file_extension = os.path.splitext(img_name)
    
    if file_extension not in {'.exr', '.png', '.jpg', '.jpeg', '.EXR', '.PNG', '.JPG', '.JPEG'}:
        cont = False
        print(file_extension)
        raise Exception("Please make sure your files are either EXR's, PNG's, or JPEG's")

    if cont == True and file_extension == '.exr':
        img = cv2.imread(img_path, -1)
        img = img * 65535
        img[img > 65535] = 65535
        img = np.uint16(img)
        
        png_name = img_name.replace('.exr', '.png')
        full_output_path = os.path.join(temp_dir, png_name)
        cv2.imwrite(full_output_path, img)

    elif cont == True and file_extension != '.exr':
        shutil.copy(dir_path + '/' + img_name, temp_dir)

def get_file_paths(cache_dir):
    """Walk through a directory and return sorted list of file paths."""
    file_paths = []
    for dirpath, _, filenames in os.walk(cache_dir):
        file_paths.extend([os.path.join(dirpath, filename) for filename in sorted(filenames)])
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
    extended_files_list = [extend_list_to_length(files, max_length) for files in files_list]

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