"""Run MaaEnd tasks headless through MaaPiCli.

MaaPiCli resolves the project (interface.json, resources, agents) from the folder of its
own executable, which in the release bundle is vendor/maaend/maafw. `prepare()` links the
project files into that folder and writes an interface.json that MaaPiCli can parse.
"""

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from endfield import ROOT, jsonc, overrides
from endfield.config import Config
from endfield.vendor import PICLI, VENDOR

PI_DIR = PICLI.parent
OUR_LAYER = ROOT / "resources" / "endfield"
LINKED = ["resource", "resource_adb", "tasks", "locales", "agent", "data"]

# Imports that use features the bundled MaaPiCli can't parse and that ADB doesn't need.
# Keymap.json defines PC keyboard bindings with the `hotkey` option type.
SKIP_IMPORTS = {"tasks/setting/Keymap.json"}


def interface() -> dict:
    data = jsonc.load(VENDOR / "interface.json")
    data["import"] = [p for p in data["import"] if p not in SKIP_IMPORTS]
    # Don't pass MaaEnd's Sentry DSN on to agents; our runs shouldn't report to it.
    data.pop("telemetry", None)
    # Load our layers after MaaEnd's ADB layer: generated Traditional Chinese OCR text,
    # then hand-written fixes (resources/endfield).
    for ctrl in data["controller"]:
        if ctrl["name"] == "ADB":
            ctrl["attach_resource_path"] = [
                *ctrl["attach_resource_path"],
                str(overrides.LAYER),
                str(OUR_LAYER),
            ]
    return data


def prepare() -> Path:
    overrides.build()
    for name in LINKED:
        link = PI_DIR / name
        if not link.is_symlink():
            link.symlink_to(Path("..") / name)
    # Agents run with MaaPiCli's folder as cwd but load MaaFramework from ./maafw.
    self_link = PI_DIR / "maafw"
    if not self_link.is_symlink():
        self_link.symlink_to(".")
    (PI_DIR / "interface.json").write_text(
        json.dumps(interface(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return PI_DIR


@dataclass
class Task:
    name: str
    # Option name -> case name (select/switch), list of cases (checkbox),
    # or dict of input values (input).
    options: dict[str, str | list[str] | dict[str, str]] = field(default_factory=dict)

    def to_config(self) -> dict:
        opts = []
        for name, value in self.options.items():
            if isinstance(value, list):
                opts.append({"name": name, "values": value})
            elif isinstance(value, dict):
                opts.append({"name": name, "inputs": value})
            else:
                opts.append({"name": name, "value": value})
        return {"name": self.name, "option": opts}


def known_options() -> tuple[set[str], dict[str, dict]]:
    """Task names and all option definitions in the generated interface."""
    data = interface()
    tasks, options = set(), dict(data.get("option", {}))
    for t in data.get("task", []):
        tasks.add(t["name"])
    for imp in data["import"]:
        d = jsonc.load(VENDOR / imp)
        tasks |= {t["name"] for t in d.get("task", [])}
        options.update(d.get("option") or {})
    return tasks, options


def _task_defs() -> dict[str, dict]:
    data = interface()
    defs = {t["name"]: t for t in data.get("task", [])}
    for imp in data["import"]:
        defs.update({t["name"]: t for t in jsonc.load(VENDOR / imp).get("task", [])})
    return defs


def validate(tasks: list[Task]) -> list[str]:
    """Problems with task or option names/values, so typos fail before touching the phone."""
    names, options = known_options()
    task_defs = _task_defs()
    problems = []
    for t in tasks:
        if t.name not in names:
            problems.append(f"unknown task {t.name}")
        for opt, value in t.options.items():
            o = options.get(opt)
            if o is None:
                problems.append(f"{t.name}: unknown option {opt}")
                continue
            if o.get("type") == "input":
                allowed = {i["name"] for i in o.get("inputs", [])}
                bad = set(value) - allowed if isinstance(value, dict) else {"<not a mapping>"}
            else:
                allowed = {c["name"] for c in o.get("cases", [])}
                values = value if isinstance(value, list) else [value]
                bad = {str(v) for v in values} - allowed
            if bad:
                problems.append(f"{t.name}: {opt} has no {sorted(bad)} (allowed: {sorted(allowed)[:8]})")
        # MaaPiCli doesn't apply a checkbox's default when the option is left out, so a
        # missing 執行週期 means "no days" and the task silently skips.
        task_def = task_defs.get(t.name, {})
        for opt in task_def.get("option") or []:
            if opt.endswith("Schedule") and opt not in t.options:
                problems.append(f"{t.name}: set {opt} explicitly (left out, MaaEnd runs on no days)")
    return problems


def pi_config(cfg: Config, tasks: list[Task]) -> dict:
    return {
        "controller": {"name": "ADB"},
        # At run time MaaPiCli fills in screencap/input methods only for a device whose
        # name and adb_path match MaaToolkit's scan, which names devices "<serial>-<adb>".
        "adb": {"name": f"{cfg.serial}-{cfg.adb}", "adb_path": cfg.adb, "address": cfg.serial},
        "resource": "官服",
        "task": [t.to_config() for t in tasks],
    }


def _shims(run_dir: Path) -> Path:
    shims = VENDOR.parent / "shims"
    shims.mkdir(exist_ok=True)
    opener = shims / "open"
    opener.write_text(f'#!/bin/sh\necho "$@" >> "{run_dir / "opened_urls.txt"}"\n')
    opener.chmod(0o755)
    return shims


_TASK_EVENT = re.compile(rb"msg=Tasker\.Task\.(Succeeded|Failed)\] \[details=\{\"entry\":\"([^\"]+)\"")


def task_results(maafw_log: bytes) -> list[tuple[str, bool]]:
    """(entry, succeeded) for each finished task, in order, from maafw.log."""
    return [(e.decode(), r == b"Succeeded") for r, e in _TASK_EVENT.findall(maafw_log)]


def run(cfg: Config, tasks: list[Task], run_dir: Path, timeout: float = 3600) -> bool:
    """Run tasks with `MaaPiCli -d`; logs go to run_dir. Returns True on success.

    MaaPiCli's exit code can't be trusted (its signal handler exits 0, even on a crash),
    and it prints "All tasks have been completed" even when a task failed. Success means
    maafw.log has a Tasker.Task.Succeeded event for every task and no Failed event.
    """
    prepare()
    conf = PI_DIR / "config" / "maa_pi_config.json"
    conf.parent.mkdir(exist_ok=True)
    conf.write_text(
        json.dumps(pi_config(cfg, tasks), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    shutil.copy(conf, run_dir / "maa_pi_config.json")
    log = PI_DIR / "debug" / "maafw.log"
    agent_log = PI_DIR / "debug" / "go-service.log"
    # Both logs append across runs; start each run with fresh ones.
    log.unlink(missing_ok=True)
    agent_log.unlink(missing_ok=True)
    # MaaFramework rotates maafw.log to maafw.bak.<time>.log when it grows large.
    for old in PI_DIR.glob("debug/maafw.bak.*.log"):
        old.unlink()
    # MaaToolkit's device scan only finds devices from an adb on PATH. The shim dir comes
    # first: IntelArchive opens its result in a browser with `open <url>`, which would
    # import every run into the user's Open Endfieldmap progress; the shim only logs it.
    env = {
        **os.environ,
        "PATH": os.pathsep.join([str(_shims(run_dir)), str(Path(cfg.adb).parent), os.environ["PATH"]]),
    }
    out_path = run_dir / "maapicli.log"
    with out_path.open("wb") as out:
        try:
            code = subprocess.run(
                [PICLI, "-d"],
                cwd=PI_DIR,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=out,
                timeout=timeout,
            ).returncode
        except subprocess.TimeoutExpired:
            out.write(f"\n### endfield: timed out after {timeout:.0f}s ###\n".encode())
            code = -1
    if agent_log.exists():
        shutil.copy(agent_log, run_dir / "go-service.log")
    if not log.exists():
        return False
    parts = sorted(PI_DIR.glob("debug/maafw.bak.*.log")) + [log]
    with (run_dir / "maafw.log").open("wb") as merged:
        for part in parts:
            merged.write(part.read_bytes())
    results = task_results((run_dir / "maafw.log").read_bytes())
    return code == 0 and len(results) == len(tasks) and all(ok for _, ok in results)
