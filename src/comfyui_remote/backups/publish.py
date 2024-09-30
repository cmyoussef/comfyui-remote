# standard imports
import json
import logging
import os
import shutil
import argparse

# dneg imports
from astrohub.context import PublishContext
from pipepublish_utils.v1.astrotransition import context_to_info_dict
import pipepublish

# dnnuke imports
from dnnuke.globals import ash, NukeHandler
import nuke

# local imports
from .. import generator as _generator

_LOGGER = logging.getLogger(__name__)

try:
    FileNotFoundError
except NameError:
    FileNotFoundError = IOError

TWIGTYPE_PREFIX = "DMP"

class EXRPublisher:
    """The publisher class for EXR, PNG, and JPEG."""

    def __init__(self):
        self._ash = ash.dataObject()
        self.version_info = {}
        self.published_file_path = None
        self.stalk_dnuuid = None
        self.stalk_name = None

    def initUIKit(self, job, stem):
        """Initialise the ui kit with the show, shot and twigtype."""
        publish_context = PublishContext(
            self._ash, job=job, stem=stem, twigType=TWIGTYPE_PREFIX.lower()
        )
        publisher = self._ash.getPublisher()
        publisher.setPublishContext(publish_context)
        generator = _generator.DMPGenerator(publisher)
        generator.buildOptions()
        self.publish_context = publish_context

    def _populatePublishList(self, folder_path):
        """Loops over a folder to find the files to query for publish."""
        if not os.path.isdir(folder_path):
            return False

        self.file_path_map = {}
        
        metadata_path = os.path.join(folder_path, "metadata.json")
        if os.path.exists(metadata_path):
            self.metadata_file = os.path.basename(metadata_path)
            self._addFileToPublish(metadata_path)

        for file_name in os.listdir(folder_path):
            if file_name.lower().endswith((".exr", ".png", ".jpeg", ".jpg")):
                self._addFileToPublish(os.path.join(folder_path, file_name))

        return True

    def _addFileToPublish(self, path):
        """Add a file to a dictionary that queries file publishes."""
        file_name = os.path.basename(path)
        self.file_path_map.update({file_name: path})

    def publish(self):
        """Publish the selected files along with session data."""
        valid_ivy_config, msg = self.publish_context.isValid()
        if not valid_ivy_config:
            print(f"Unable to publish: {msg}")
            return

        try:
            version_info = context_to_info_dict(self.publish_context)
            version_info["appname"] = "rndnuke"
            version_info["appversion"] = nuke.NUKE_VERSION_STRING

            framerange = self.publish_context.getStalkAttr("framerange")
            if framerange is None:
                framerange = "1001-1001"

            files_info = []
            for file_name, path in self.file_path_map.items():
                file_info = {
                    "type": pipepublish.v1.FileType.GENERATED,
                    "path": path,
                    "prefix": os.path.splitext(file_name)[0],
                    "frame_range": framerange,
                }
                files_info.append(file_info)

            version_info["files"] = files_info

            version_result = pipepublish.v1.open_new_version(version_info)
            session_id = version_result["session_id"]

            try:
                with version_result:
                    for file in version_result["files"]:
                        file_name = os.path.basename(file["path"])
                        source_path = self.file_path_map[file_name]

                        # Get destination path and copy files.
                        destination_path = file["path"]
                        shutil.copyfile(source_path, destination_path)

                        # If it is the multilayer destination, grab the path to replace
                        # the source read in the DMP Publisher wrapper.
                        if destination_path.endswith(("exr", "png", "jpeg", "jpg")):
                            self.published_file_path = destination_path
                            self.stalk_name = os.path.basename(
                                os.path.dirname(destination_path)
                            )
                            self.stalk_dnuuid = version_result["id"]

            except Exception:
                pipepublish.v1.close_version(
                    {"session_id": session_id, "error": True}
                )
                # Reset instance variables.
                self.stalk_name = None
                self.stalk_dnuuid = None
                self.published_file_path = None
                print("Publish failed. Check exports and the error log.")
                raise

        finally:
            if self.stalk_name:
                print(f"Publish Successful: {self.stalk_name}")
            else:
                print("Publish Failed. Please verify configuration and try again.")

def main():
    parser = argparse.ArgumentParser(description="Publish EXR, PNG, JPEG files.")
    parser.add_argument("folder_path", help="Path to the folder containing the files to publish.")
    parser.add_argument("job", help="The show we are publishing to.")
    parser.add_argument("stem", help="The shot we are publishing to, can be None.")
    
    args = parser.parse_args()
    
    publisher = EXRPublisher()
    publisher.initUIKit(job=args.job, stem=args.stem)
    
    if publisher._populatePublishList(args.folder_path):
        publisher.publish()
    else:
        print("No valid files found to publish.")

if __name__ == "__main__":
    main()
