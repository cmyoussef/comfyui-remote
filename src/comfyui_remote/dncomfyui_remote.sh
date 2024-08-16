#!/bin/bash

### Get latest ComfyUI Directory
COMFY_BASE_PATH=/tools/SITE/rnd/comfyUI

# Find the latest comfyui version folder
latest_version=$(ls -d $COMFY_BASE_PATH/comfyui-* | sort -V | tail -n 1 | awk -F'-' '{print $2}')

# Use the latest version
COMFY_VERSION=$latest_version

echo "DNEG ComfyUI $COMFY_VERSION"

COMFY_VERSION_PATH=$COMFY_BASE_PATH/comfyui-$COMFY_VERSION


COMFY_REMOTE_DEV_PATH=/u/gdso/DNEG/dev/gabriel-souza
### Get latest ComfyUI_remote Directory
latest_remote_version=$(ls -d $COMFY_REMOTE_DEV_PATH/comfyui_remote-* | sort -V | tail -n 1 | awk -F'-' '{print $2}')

# Use the latest version
COMFY_REMOTE_VERSION=$latest_remote_version

echo "DNEG ComfyUI Remote $COMFY_REMOTE_VERSION"

COMFY_REMOTE_VERSION_PATH=$COMFY_REMOTE_DEV_PATH/comfyui_remote-$COMFY_REMOTE_VERSION

echo "COMFY_REMOTE_VERSION_PATH is $COMFY_REMOTE_VERSION_PATH"

COMFY_MAIN_PY="$COMFY_VERSION_PATH/ComfyUI/main.py"
# make sure we are in the ComfyUI folder
if [ ! -f $COMFY_MAIN_PY ]
then
	echo "could not find $COMFY_MAIN_PY"
	echo "invalid installation or comfyui version, aborting"
	exit 1
fi

if [ -f "/opt/conda/etc/profile.d/conda.sh" ]; then
    . "/opt/conda/etc/profile.d/conda.sh"
  else
    export PATH="/opt/conda/bin:$PATH"
fi

export PYTHONPATH=""
conda activate "$COMFY_VERSION_PATH"

# Prompt the user for inputs
read -p "Enter the path for --json_file: " json_file
read -p "Enter the path for --input_dir: " input_dir
read -p "Enter the value for --batch_size: (default=1) " batch_size

# Navigate to the target directory
pushd `pwd`
cd $COMFY_REMOTE_VERSION_PATH/ComfyUI_remote

# Execute the Python script with user inputs
python ./launcher.py --json_file "$json_file" --input_dir "$input_dir" --batch_size "$batch_size"
popd