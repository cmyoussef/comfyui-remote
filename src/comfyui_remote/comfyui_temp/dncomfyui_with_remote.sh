#!/bin/bash
# sicp 02/2024

# TODO TEMPORARY this should be added to general.data and removed here
DN_COMFYUI_VERSION=1.0.5

# default from general.dat
COMFY_VERSION=$DN_COMFYUI_VERSION

COMFY_BASE_PATH=/tools/SITE/rnd/comfyUI
COMFY_VERSION_PATH=$COMFY_BASE_PATH/comfyui-$COMFY_VERSION

COMFY_MAIN_PY="$COMFY_VERSION_PATH/ComfyUI/main.py"

echo "DNEG ComfyUI $COMFY_VERSION"

# make sure we are in the ComfyUI folder
if [ ! -f $COMFY_MAIN_PY ]; then
    echo "could not find $COMFY_MAIN_PY"
    echo "invalid installation or comfyui version, aborting"
    exit 1
fi

# make sure conda is available
if [ -f "/opt/conda/etc/profile.d/conda.sh" ]; then
    . "/opt/conda/etc/profile.d/conda.sh"
else
    export PATH="/opt/conda/bin:$PATH"
fi

# default for remote flag
REMOTE=false

# read_char var
read_char() {
  stty -icanon -echo
  eval "$1=\$(dd bs=1 count=1 2>/dev/null)"
  stty icanon echo
}

# check if comfy is already running
COMFY_INSTANCES_RUNNING=$(ps ux | grep python | grep cuda | grep main.py | awk '{print $2;}' | wc -l)
if [ $COMFY_INSTANCES_RUNNING -gt 0 ]; then
    echo "################################################################################################"
    echo "You already appear to have $COMFY_INSTANCES_RUNNING instance(s) of ComfyUI running on $HOSTNAME"
    echo "Enter 'y' to kill those instances and start a fresh one, or press any other key to exit"
    read_char USER_INPUT_CHARACTER
    if [[ $USER_INPUT_CHARACTER == "y" ]]; then
        echo "Attempting to kill running ComfyUI instances"
        ps ux | grep python | grep cuda | grep main.py | awk '{print $2;}' | xargs sudo kill
        COMFY_INSTANCES_RUNNING=$(ps ux | grep python | grep cuda | grep main.py | awk '{print $2;}' | wc -l)
        echo "You now have $COMFY_INSTANCES_RUNNING instance(s) of ComfyUI running on $HOSTNAME"
        if [ $COMFY_INSTANCES_RUNNING -ne 0 ]; then
            echo "Could not kill all running instances, exiting"
            exit 1
        fi
        echo "Proceeding with normal startup..."
        echo "################################################################################################"
    else
        echo "Exiting"
        exit 0
    fi
else
    echo "No running ComfyUI instances detected, proceeding with normal startup..."
fi

set -eo pipefail

# FIXME this does not work
POSITIONAL_ARGS=()

# check if user has provided a version or remote flag on the command line
while [[ $# -gt 0 ]]; do
    case "$1" in
        -v|--version)
            shift
            COMFY_VERSION=$1
            ;;
        -h|--help)
            echo "dncomfyui - DNEG ComfyUI wrapper script"
            echo ""
            echo "Usage:"
            echo "-v|--version : request a specific version, overwrite DN_COMFYUI_VERSION"
            echo "-r|--remote  : use the latest remote version of ComfyUI"
            echo "-h|--help    : you are looking at it"
            echo "additional parameters (e.g., --lowvram) are passed on into ComfyUI."
            echo ""
            exit 0
            ;;
        -r|--remote)
            REMOTE=true
            ;;
        *)
            POSITIONAL_ARGS+=("$1")
    esac
    shift
done

if [ "$REMOTE" = true ]; then
    # Get latest ComfyUI_remote Directory
    latest_remote_version=$(ls -d $COMFY_BASE_PATH/comfyui_remote-* | sort -V | tail -n 1 | awk -F'-' '{print $2}')

    # Use the latest version
    COMFY_REMOTE_VERSION=$latest_remote_version

    echo "DNEG ComfyUI Remote $COMFY_REMOTE_VERSION"

    COMFY_REMOTE_VERSION_PATH=$COMFY_BASE_PATH/comfyui_remote-$COMFY_REMOTE_VERSION

    echo "COMFY_REMOTE_VERSION_PATH is $COMFY_REMOTE_VERSION_PATH"

    # Prompt the user for inputs
    read -p "Enter the path for --json_file: " json_file
    read -p "Enter the path for --input_dir: " input_dir
    read -p "Enter the value for --batch_size: (default=1) " batch_size

    # Navigate to the target directory
    pushd `pwd`

    export PYTHONPATH=""

    conda activate "$COMFY_VERSION_PATH"
    echo "conda activated"

    cd $COMFY_REMOTE_VERSION_PATH/ComfyUI_remote

    # Execute the Python script with user inputs
    python ./launcher.py --json_file "$json_file" --input_dir "$input_dir" --batch_size "${batch_size:-1}"
    popd
else

    CHROME_VERSION=$(chrome --version | awk '{print $3;}' | sed 's/\..*$//g')
    CHROME_VERSION_FULL=$(chrome --version | awk '{print $3;}')
    if [ $CHROME_VERSION -ge 119 ]; then
        echo "#################################################"
        echo "Found supported Chrome version ($CHROME_VERSION_FULL)."
        echo "#################################################"
    else
        echo "#################################################"
        echo "Found unsupported Chrome version $CHROME_VERSION_FULL."
        echo "Please ask support@dneg.com to upgrade your Chrome version. ComfyUI requires at least Chrome 119."
        echo "#################################################"
        exit 1
    fi

    COMFY_LOCAL_BASE_PATH="/user_data/comfyui"
    COMFY_OUTPUT_PATH="$COMFY_LOCAL_BASE_PATH/output"
    COMFY_INPUT_PATH="$COMFY_LOCAL_BASE_PATH/input"
    COMFY_TEMP_PATH="$COMFY_LOCAL_BASE_PATH/temp"
    mkdir -p $COMFY_OUTPUT_PATH
    mkdir -p $COMFY_INPUT_PATH
    mkdir -p $COMFY_TEMP_PATH
    echo "############################################################"
    echo "####################### IMPORTANT ##########################"
    echo "############################################################"
    echo "Your output images will get saved under $COMFY_OUTPUT_PATH."
    echo "Your input images will get stored under $COMFY_INPUT_PATH."
    echo "############################################################"

    export PYTHONPATH=""

    conda activate "$COMFY_VERSION_PATH"
    echo "conda activated"


    pushd `pwd`
    cd $COMFY_VERSION_PATH/ComfyUI
    #python -c "import torch;print(torch.cuda.is_available())"
    echo "running: python -W ignore::DeprecationWarning ./main.py --disable-cuda-malloc ${POSITIONAL_ARGS[@]+${POSITIONAL_ARGS[@]}} --output-directory $COMFY_OUTPUT_PATH"
    python -W ignore::DeprecationWarning ./main.py --disable-cuda-malloc "${POSITIONAL_ARGS[@]+${POSITIONAL_ARGS[@]}}" --output-directory "$COMFY_OUTPUT_PATH" --temp-directory "$COMFY_TEMP_PATH" --input-directory "$COMFY_INPUT_PATH"
    popd
fi
