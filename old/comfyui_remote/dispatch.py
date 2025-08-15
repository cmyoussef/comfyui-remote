# coding=utf-8
"""Module to dispatch ComfyUI jobs in CARDS."""

# Standard Library Imports
import logging
import os
import re

try:
    # DNEG Imports
    import cards
    import spider
except ImportError:
    cards = None
    spider = None

from comfyui_remote.config import DEFAULT_SHOW, DEFAULT_SHOT, SERVICE_KEYS

logger = logging.getLogger(__name__)

COMFY_REMOTE_BOB_TARGET = "platform-pipe5-1"


def build_graph(job, shot, workflow, on_farm=False):
    """Build Cards action graph for ComfyUI workflow execution.

    Create an action graph to execute a ComfyUI workflow using the CARDS system.
    The graph includes the necessary context and command setup for running the
    workflow either locally or on the farm.

    Args:
        job (str): The job/show name for the workflow execution.
        shot (str): The shot name for the workflow execution.
        workflow (str): The path to the ComfyUI workflow JSON file.
        on_farm (bool, optional): Determines whether the graph runs locally or on the
            farm. If False, adds local execution prefix to the command.
            Default is False.

    Returns:
        tuple: A tuple containing (handler, graph) where:
            - handler (cards.core.handler.ActionHandler): The CARDS action handler.
            - graph (cards.core.action.ActionGraph): The configured action graph
              for ComfyUI workflow execution.
    """
    spider_handler = spider.getHandler()
    handler = cards.getHandler(spider_handler)
    stem = spider_handler["Stem"].one(
        spider_handler["Stem"]["job"] == job,
        spider_handler["Stem"]["stemname"] == shot,
    )

    workflow_name = os.path.basename(workflow)

    graph = handler.createAction("ActionGraph")
    graph.name = f"Comfy Remote:{workflow_name}"
    graph.context = handler.createContext(
        job=stem["job"],
        stem=stem,
        workspacetype="server",
    )
    graph.context.bobtarget = COMFY_REMOTE_BOB_TARGET

    run_command = handler.createAction("RunCommand")
    run_command.name = "ComfyUI Remote command"
    cmd = f"comfy-remote --batch-size 1 --run {workflow}"

    if not on_farm:
        local_run_prefix = f"bob-world -t {COMFY_REMOTE_BOB_TARGET} -- "
        cmd = local_run_prefix + cmd

    logger.info("ComfyUI command: %s", cmd)
    run_command.setup(command=cmd)
    run_command.settings.execution_options = {"service": SERVICE_KEYS}
    graph.add(run_command)

    return handler, graph


def log_dispatch_results(jid):
    """Log the results of the dispatch operation.

    Logs a formatted message indicating successful job submission with the
    Tractor job ID and a URL to view the job in the Tractor web interface.

    Args:
        jid (int): The Tractor job ID of the submitted job.
    """
    margin = " " * 22

    msg = (
        f"JOB SUBMITTED 🚀 \n"
        f"{margin} Tractor jid     : {jid}\n"
        f"{margin} URL             : http://tractor/tv/#jid={jid}\n"
    )

    logger.info(msg)


def dispatch(
    workflow,
    job=None,
    shot=None,
    frame_range=None,
    on_farm=True,
):
    """Dispatch a ComfyUI workflow execution job.

    Execute a dispatch operation for running a ComfyUI workflow either locally
    or on the farm using the CARDS/Tractor system.

    Args:
        workflow (str): The path to the ComfyUI workflow JSON file for execution.
        job (str, optional): Show name. If not provided, defaults to the SHOW
            environment variable or DEFAULT_SHOW.
        shot (str, optional): Shot name. If not provided, defaults to the SHOT
            environment variable or DEFAULT_SHOT.
        frame_range (str, optional): Frame range for rendering. Currently not
            used in the implementation but reserved for future functionality.
        on_farm (bool): If True, runs the dispatch on the farm using Tractor.
            If False, runs locally. Default is True.

    Returns:
        dict: A dictionary mapping shot name to job ID (jid). The jid is the
            Tractor job ID if running on farm, 0 for local execution, or -1
            if there was an error.

    Raises:
        RuntimeError: When the dispatch job fails to launch.
    """
    job = job or os.environ.get("SHOW", DEFAULT_SHOW)
    shot = shot or os.environ.get("SHOT", DEFAULT_SHOT)

    handler, action_graph = build_graph(
        job=job,
        shot=shot,
        workflow=workflow,
        on_farm=on_farm,
    )

    jid = -1  # error
    if on_farm:
        tractor_job = handler.dispatch(action_graph)
        if tractor_job and tractor_job.code == 0:
            jid_match = re.search(r"jid:\s*(\d+)", tractor_job.result)
            if jid_match:
                jid = int(jid_match.group(1))
                log_dispatch_results(jid)
        else:
            logger.error("Tractor submission failed.")
    else:
        logger.info("Submitting locally")
        handler.run(action_graph)
        jid = 0

    return {shot: jid}


if __name__ == "__main__":
    workflow = "/jobs/ADGRE/ASSET/ivy/ref/REF_ADGRE_comp_comfyui_template_batchTesting_v006/REF_ADGRE_comp_comfyui_template_batchTesting_v006.json"
    job = "ADGRE"
    shot = "pdev_comp"
    frame_range = "1004-1020"
    on_farm = True
    dispatch(workflow, job, shot, frame_range, on_farm)
