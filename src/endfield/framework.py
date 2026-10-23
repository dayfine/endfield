"""MaaFramework session over ADB, for checks and scans we run outside MaaPiCli."""

from pathlib import Path

from endfield.vendor import VENDOR


def connect(adb: str, serial: str, log_dir: Path, bundles=("resource", "resource_adb")):
    """Tasker bound to MaaEnd's resource layers and the phone."""
    from maa.controller import AdbController
    from maa.resource import Resource
    from maa.tasker import Tasker
    from maa.toolkit import Toolkit

    Toolkit.init_option(str(log_dir))
    res = Resource()
    for bundle in bundles:
        res.post_bundle(str(VENDOR / bundle)).wait()
    ctl = AdbController(adb, serial)
    if not ctl.post_connection().wait().succeeded:
        raise RuntimeError("MaaFramework could not connect to the device")
    tasker = Tasker()
    tasker.bind(res, ctl)
    if not tasker.inited:
        raise RuntimeError("MaaFramework tasker did not initialise")
    # Keep the resource and controller alive as long as the tasker.
    tasker._endfield_refs = (res, ctl)
    return tasker


def in_world(tasker) -> bool:
    """MaaEnd's InWorld node: the open-world HUD is on screen."""
    job = tasker.post_task("InWorld", {"InWorld": {"timeout": 3000}}).wait()
    return job.get().status.succeeded
