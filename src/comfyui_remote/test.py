import os
import subprocess
import ast
from pathlib import Path
import re
import shutil


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
    if imgs:
        for i in imgs:
            shutil.copy(im_path + "/" + i, temp_dir)
    else:
        raise Exception("No images found inside input path")


# transfer_imgs_from_path("/user_data/comfyui/output/012", "/hosts/lonws2351/user_data/comfyUI_output")


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


# img_list = ["/user_data/comfyui/output/012/depthPro.1001.exr", "/user_data/comfyui/output/012/depthPro.1002.exr", "/user_data/comfyui/output/012/depthPro.1003.exr"]

# transfer_imgs_from_list(img_list, "/hosts/lonws2351/user_data/comfyUI_output")


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


transfer_single_img(
    "/user_data/comfyui/output/012/depthPro.1001.exr",
    "/hosts/lonws2351/user_data/comfyUI_output",
)
