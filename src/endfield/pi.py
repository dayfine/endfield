"""Run MaaEnd tasks headless through MaaPiCli.

MaaPiCli resolves the project (interface.json, resources, agents) from the folder of its
own executable, which in the release bundle is vendor/maaend/maafw. `prepare()` links the
project files into that folder and writes an interface.json that MaaPiCli can parse.
"""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from endfield import jsonc
from endfield.config import Config
from endfield.vendor import PICLI, VENDOR

PI_DIR = PICLI.parent
LINKED = ["resource", "resource_adb", "tasks", "locales", "agent", "data"]

# Imports that use features the bundled MaaPiCli can't parse and that ADB doesn't need.
# Keymap.json defines PC keyboard bindings with the `hotkey` option type.
SKIP_IMPORTS = {"tasks/setting/Keymap.json"}


def interface() -> dict:
    data = jsonc.load(VENDOR / "interface.json")
    data["import"] = [p for p in data["import"] if p not in SKIP_IMPORTS]
    # Don't pass MaaEnd's Sentry DSN on to agents; our runs shouldn't report to it.
    data.pop("telemetry", None)
    return data


def prepare() -> Path:
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


def pi_config(cfg: Config, tasks: list[Task]) -> dict:
    return {
        "controller": {"name": "ADB"},
        # At run time MaaPiCli fills in screencap/input methods only for a device whose
        # name and adb_path match MaaToolkit's scan, which names devices "<serial>-<adb>".
        "adb": {"name": f"{cfg.serial}-{cfg.adb}", "adb_path": cfg.adb, "address": cfg.serial},
        "resource": "官服",
        "task": [t.to_config() for t in tasks],
    }


SUCCESS = b"All tasks have been completed"


def run(cfg: Config, tasks: list[Task], run_dir: Path, timeout: float = 3600) -> bool:
    """Run tasks with `MaaPiCli -d`; logs go to run_dir. Returns True on success.

    MaaPiCli's exit code can't be trusted (its signal handler exits 0, even on a crash),
    so success means the completion line appears in its output.
    """
    prepare()
    conf = PI_DIR / "config" / "maa_pi_config.json"
    conf.parent.mkdir(exist_ok=True)
    conf.write_text(
        json.dumps(pi_config(cfg, tasks), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    shutil.copy(conf, run_dir / "maa_pi_config.json")
    log = PI_DIR / "debug" / "maafw.log"
    log.unlink(missing_ok=True)
    # MaaToolkit's device scan only finds devices from an adb on PATH.
    env = {**os.environ, "PATH": f"{Path(cfg.adb).parent}{os.pathsep}{os.environ['PATH']}"}
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
    if log.exists():
        shutil.copy(log, run_dir / "maafw.log")
    return code == 0 and SUCCESS in out_path.read_bytes()
