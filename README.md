# comfyui-remote

_Description:_ A serverless implementation for running ComfyUI workflows.

## Usage

## Documentation

The full docs of every published version are available [here](http://i/tools/SITE/doc/comfyui-remote/comfyui-remote).


The User Documentation is [available on dnet](http://dnet.dneg.com/display/PRODTECH/comfyui-remote) and is updated upon any release.


## Contributing

Our [guidelines](http://dnet.dneg.com/display/PRODTECH/Submitting+and+Reviewing+Code) outline every step to submit your code for review.

As a team we use PEP-0008 as a style guide.
You can run an automated style check on the project by calling:

    python setup.py flake8

from the project root.

## Deploying


This project uses python [setuptools](https://setuptools.readthedocs.io/en/latest/) to build the python package in an effort to make it available to different distribution systems, including bob.
The source can be built and distributed via [dnpkg](http://intranet/tools/SITE/rnd/doc/dnpkg/workflow.html#using-dnpkg). The [usage section](http://intranet/tools/SITE/rnd/doc/dnpkg/workflow.html#using-dnpkg) and the explaination of what a [dnpkg target](http://intranet/tools/SITE/rnd/doc/dnpkg/gettingstarted.html#targets) is are particularly relevant.

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

