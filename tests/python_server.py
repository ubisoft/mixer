import argparse
import asyncio
import logging
import struct
import sys

import bpy

from mixer.share_data import share_data
from mixer.broadcaster.common import decode_int

"""
Socket server for Blender that receives python strings, compiles
and executes them
To be used by tests for "remote controlling" Blender :
blender.exe --python python_server.py -- --port=8989

Requires AsyncioLoopOperator

Adapted from
https://blender.stackexchange.com/questions/41533/how-to-remotely-run-a-python-script-in-an-existing-blender-instance"

"""

logger = logging.getLogger("tests")
logger.setLevel(logging.INFO)
# hardcoded to avoid control from a remote machine
HOST = "127.0.0.1"
STRING_MAX = 1024 * 1024
INT_SIZE = struct.calcsize("i")


async def exec_buffer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    while True:
        buffer = await reader.read(INT_SIZE)
        length, _ = decode_int(buffer, 0)
        buffer = await reader.read(length)
        if not buffer:
            break
        addr = writer.get_extra_info("peername")
        logger.debug("-- Received %s bytes from %s", len(buffer), addr)
        logger.debug(buffer.decode("utf-8"))
        buffer_string = buffer.decode("utf-8")
        try:
            code = compile(buffer_string, "<string>", "exec")
            share_data.pending_test_update = True
            exec(code, {})
        except Exception:
            import traceback

            logger.error("Exception")
            logger.error(traceback.format_exc())
            logger.error("While processing: ")
            for i, line in enumerate(buffer_string.splitlines()):
                logger.error(f"  {i:>5} {line}")

        logger.debug("-- Done")


async def serve(port: int):
    server = await asyncio.start_server(exec_buffer, HOST, port)
    async with server:
        await server.serve_forever()


def parse():
    args_ = []
    copy_arg = False
    for arg in sys.argv:
        if arg == "--":
            copy_arg = True
        elif copy_arg:
            args_.append(arg)

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8888, help="port number to listen to")
    parser.add_argument("--ptvsd", type=int, default=5688, help="Vscode debugger port")
    parser.add_argument("--wait_for_debugger", default=False, action="store_true", help="wait for debugger")
    args, _ = parser.parse_known_args(args_)
    return args


class FailOperator(bpy.types.Operator):
    """Report test failure"""

    bl_idname = "mixer.test_fail"
    bl_label = "Report test failure"
    bl_options = {"REGISTER"}

    def execute(self, context):
        import os

        # raise SystemExit() and sys.exit() hang , so :
        os._exit(1)

        return {"FINISHED"}


timer = None

# Also see https://www.blender.org/forum/viewtopic.php?t=28331


class AsyncioLoopOperator(bpy.types.Operator):
    """
    Executes an asyncio loop, bluntly copied from
    From https://blenderartists.org/t/running-background-jobs-with-asyncio/673805

    Used by the unit tests (python_server.py)
    """

    bl_idname = "mixer.test_asyncio_loop"
    bl_label = "Test Remote"
    command: bpy.props.EnumProperty(
        name="Command",
        description="Command being issued to the asyncio loop",
        default="TOGGLE",
        items=[
            ("START", "Start", "Start the loop"),
            ("STOP", "Stop", "Stop the loop"),
            ("TOGGLE", "Toggle", "Toggle the loop state"),
        ],
    )
    period: bpy.props.FloatProperty(
        name="Period", description="Time between two asyncio beats", default=0.01, subtype="UNSIGNED", unit="TIME"
    )

    def execute(self, context):
        return self.invoke(context, None)

    def invoke(self, context, event):
        global timer
        wm = context.window_manager
        if timer and self.command in ("STOP", "TOGGLE"):
            wm.event_timer_remove(timer)
            timer = None
            return {"FINISHED"}
        elif not timer and self.command in ("START", "TOGGLE"):
            wm.modal_handler_add(self)
            timer = wm.event_timer_add(self.period, window=context.window)
            return {"RUNNING_MODAL"}
        else:
            return {"CANCELLED"}

    def modal(self, context, event):
        global timer
        if not timer:
            return {"FINISHED"}
        elif event.type != "TIMER":
            return {"PASS_THROUGH"}
        else:
            loop = asyncio.get_event_loop()
            loop.stop()
            loop.run_forever()
            return {"RUNNING_MODAL"}


class TestPanel(bpy.types.Panel):
    """Report test status"""

    bl_label = "TEST"
    bl_idname = "TEST_PT_settings"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "TEST"

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        # exit with 0 return code
        row.operator("wm.quit_blender", text="Succeed")
        # exit with non-zero return code
        row.operator(FailOperator.bl_idname, text="Fail")


classes = (FailOperator, TestPanel, AsyncioLoopOperator)


def register():
    for c in classes:
        bpy.utils.register_class(c)


if __name__ == "__main__":

    args = parse()

    if args.ptvsd:
        # do not attempt to load ptvsd by default as it tends to crash Blender
        try:
            import ptvsd  # noqa

            ptvsd.enable_attach(address=("localhost", args.ptvsd), redirect_output=True)
            if args.wait_for_debugger:
                logger.warning(f"Waiting for debugger on port {args.ptvsd}")
                ptvsd.wait_for_attach()
                logger.warning("Debugger attached")
        except ImportError:
            pass

    logger.info("Starting:")
    logger.info("  python port %s", args.port)
    logger.info("  ptvsd  port %s", args.ptvsd)
    register()
    asyncio.ensure_future(serve(args.port))
    bpy.ops.preferences.addon_enable(module="mixer")
    bpy.ops.mixer.test_asyncio_loop()
