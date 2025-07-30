# coding=utf-8
"""Module to dispatch ComfyUI jobs in CARDS."""

# Standard Library Imports
import logging
import os
import re

# DNEG Imports
import cards
import spider

DEFAULT_SHOW = "ADGRE"
DEFAULT_SHOT = "pdev_comp"
TEMPLATE_LABEL = "comfyui_dispatcher"
MLMACHINES = "workstation"  # "aimlcv, rtx_a6000", "workstation"


logger = logging.getLogger(__name__)

COMFY_REMOTE_BOB_TARGET = "platform-pipe5-1"

# Change the clunky way of publishing similar to what Nuke Remote does automatically.

# def setup_publishing(show, shot, publish_context, destination, on_farm):
#     """Setup Nuke script to be publish to Ivy.

# ....


def build_graph(job, shot, workflow, on_farm=False):
    """Build Cards action graph for bake/render.

    Create an action graph to bake and optionally render the script.

    Args:
        run_local (bool, optional): Determines whether the graph runs locally or on the
            farm.

            Running locally requires a stderr handler to view the logging statements in
            the terminal. Default is True.
        spider_handler (cobweb._portal_private.SpiderHandler): Optional `SpiderHandler`
            instance.
        handler (cards.core.handler.ActionHandler): Optional `ActionHandler` instance.

    Returns:
        CardsHandler, ActionGraph: The handler and the action graph for the bake/render.
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

    logger.info("dnComfyUI command: %s", cmd)
    run_command.setup(command=cmd)
    run_command.settings.execution_options = {"service": MLMACHINES}
    graph.add(run_command)

    return handler, graph


def log_dispatch_results(jid):
    """Log the results of the dispatch operation."""
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
    """Dispatch using the Nuke Remote Control CLI or GUI.

    Execute a dispatch operation using Nuke's Remote Control CLI or GUI, enabling
    the baking and optional rendering of a Nuke workflow.

    Args:
        workflow (str): The path to the Nuke workflow for rendering/baking.
        job (str, optional): Show name.
        shot (str, optional): Shot name.
        frame_range (str, optional): Frame range for rendering.
        overrides (dict): Dictionary of parameter overrides to apply during baking.
        on_farm (bool): Run dispatch on farm if True.

    Raises:
        RuntimeError: When the dispatch job fails to launch.
    """
    job = job or os.environ.get("SHOW", DEFAULT_SHOW)
    shot = shot or os.environ.get("SHOT", "pdev_comp")

    handler, action_graph = build_graph(
        job=job, shot=shot, workflow=workflow, on_farm=on_farm
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
    kind = "elmr"
    task = "comp"
    subtask = "precomp"
    frame_range = "1004"
    on_farm = True
    dispatch(workflow, job, shot, frame_range, on_farm=on_farm)
