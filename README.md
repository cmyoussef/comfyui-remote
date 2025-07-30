# comfyui-remote

_Description:_ A serverless/GUI implementation for batch executing ComfyUI workflows.

## Usage

### ComfyUI Remote

ComfyUI Remote is a command-line tool for executing workflows in ComfyUI by specifying a JSON file that defines the workflow and its associated parameters.

#### Basic Command

To run the tool, use the following command in your terminal:

```bash
dncomfyui -r --json_file <path_to_json> --batch_size <batch_size>
```

#### Parameters

**Required Parameters:**
- `--json_file`: Path to the JSON file containing the workflow
- `--batch_size`: The number of times you want the workflow to be executed

**Optional Parameters:**
- `--frame_range`: The range of frames for input images (format: start-end). Example: `--frame_range 0-10`
- `--int_args`: Dictionary containing any dnNode in ComfyUI that requires an integer input
- `--float_args`: Dictionary containing any dnNode in ComfyUI that requires a float input
- `--str_args`: Dictionary containing any dnNode in ComfyUI that requires a string input

#### Format for Arguments

To pass arguments for dnNodes that require integers, floats, or strings, enter them as a dictionary with the name of the dnNode and its value.

#### Example Usage

```bash
dncomfyui -r --json_file script_files/img_to_img/img2img_v018.json --batch_size 1 \
--frame_range 0-1 \
--int_args '{"Steps": 50, "Seed": 432432}' \
--str_args '{"PositivePrompt": "a cow wearing a hat", "NegativePrompt": "realistic", "inputPath": "/u/gdso/Pictures/syndata_test/imgs"}' \
--float_args '{"cnStrength": 0.8}'
```

**Explanation:**
- `--json_file`: The workflow file in JSON format
- `--batch_size`: Executes the workflow once
- `--frame_range`: Specifies the frame range from 0 to 1
- `--int_args`: Passes integer arguments to the dnNode, such as setting Steps to 50 and Seed to 432432
- `--str_args`: Specifies string arguments like prompts
- `--float_args`: Provides float values like cnStrength set to 0.8

## Documentation

The full docs of every published version are available [here](http://i/tools/SITE/doc/comfyui-remote/comfyui-remote).

The User Documentation is [available on dnet](http://dnet.dneg.com/display/PRODTECH/comfyui-remote) and is updated upon any release.

## Contributing

Our [guidelines](http://dnet.dneg.com/display/PRODTECH/Submitting+and+Reviewing+Code) outline every step to submit your code for review.

As a team we use PEP-0008 as a style guide.
You can run an automated style check on the project by calling:

```bash
python setup.py flake8
```

from the project root.

## Deploying

This project uses python [setuptools](https://setuptools.readthedocs.io/en/latest/) to build the python package in an effort to make it available to different distribution systems, including bob.
The source can be built and distributed via [dnpkg](http://intranet/tools/SITE/rnd/doc/dnpkg/workflow.html#using-dnpkg). The [usage section](http://intranet/tools/SITE/rnd/doc/dnpkg/workflow.html#using-dnpkg) and the explanation of what a [dnpkg target](http://intranet/tools/SITE/rnd/doc/dnpkg/gettingstarted.html#targets) is are particularly relevant.

### Supporting updates to multiple shows in production

The recommended way to do long term support for certain shows or releases is to create a specific release branch for a major-minor version, adding a show or feature tag if necessary. For example, a repo could have the following release branches

* master (3.1.5 released, always the latest and greatest)
* release/1.1 (long term support branch from 1.1.3 which contains critical patches to an old version: 1.1.4, 1.1.5)
* release/2-MAE (branched from the 2.5 release, will include new MAE specific minor and patch updates)

## Testing

Tests can be performed under multiple application environments using the [hum framework](http://i/tools/SITE/doc/hum/hum/index.html).

Launch `hum test` in the shell to run the entire test suite.

## Contacts

td@redefine.co