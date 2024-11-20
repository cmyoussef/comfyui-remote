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

# add everything below to dncomfyui bash script
# Default values
json_file=""
batch_size=1
frame_range=None
int_args=None
float_args=None
str_args=None

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --json_file) json_file="$2"; shift ;;
        --batch_size) batch_size="$2"; shift ;;
        --frame_range) frame_range="$2"; shift ;;
        --int_args) int_args="$2"; shift ;;
        --float_args) float_args="$2"; shift ;;
        --str_args) str_args="$2"; shift ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

# Check if json_file was provided
if [ -z "$json_file" ]; then
    echo "Error: --json_file is required"
    exit 1
fi

# Navigate to the target directory
pushd `pwd`
cd $COMFY_REMOTE_VERSION_PATH/ComfyUI_remote

# Execute the Python script with the provided inputs
python ./launcher.py --json_file "$json_file" --batch_size "$batch_size" --frame_range "$frame_range"  --int_args "$int_args" --float_args "$float_args" --str_args "$str_args"
popd