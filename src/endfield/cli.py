import argparse
import datetime as dt
from pathlib import Path

from endfield import ROOT, config, pi, vendor
from endfield.device import Device


def _run_dir() -> Path:
    path = ROOT / "runs" / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path.mkdir(parents=True, exist_ok=True)
    return path


def cmd_fetch(args: argparse.Namespace) -> int:
    vendor.fetch(force=args.force)
    return 0


def cmd_device_check(args: argparse.Namespace) -> int:
    dev = Device(config.load())
    if not dev.is_connected():
        print(f"device {dev.cfg.serial} not connected")
        return 1
    info = dev.info()
    for key, value in vars(info).items():
        print(f"{key:14} {value}")
    print(f"{'screenshot':14} {dev.screenshot(_run_dir() / 'check.png')}")
    return 0


def cmd_screenshot(args: argparse.Namespace) -> int:
    dev = Device(config.load())
    print(dev.screenshot(args.out or _run_dir() / "screen.png"))
    return 0


def cmd_size(args: argparse.Namespace) -> int:
    dev = Device(config.load())
    if args.mode == "force":
        dev.set_size(dev.cfg.force_size)
    elif args.mode == "reset":
        dev.set_size(None)
    physical, override = dev.sizes()
    print(f"physical {physical}  override {override or '-'}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    cfg = config.load()
    dev = Device(cfg)
    if not dev.is_connected():
        print(f"device {cfg.serial} not connected")
        return 1
    tasks = [pi.Task(name) for name in args.tasks]
    for task in tasks:
        if task.name in ("AndroidOpenGame", "CloseGame"):
            task.options["ClientVersion"] = cfg.client_version
    run_dir = _run_dir()
    with dev.forced_size():
        ok = pi.run(cfg, tasks, run_dir)
        if not ok:
            dev.screenshot(run_dir / "failure.png")
    print(f"{'ok' if ok else 'failed'}: logs in {run_dir}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="endfield")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("fetch", help="download the pinned MaaEnd bundle into vendor/")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_fetch)

    dev = sub.add_parser("device", help="device commands").add_subparsers(required=True)
    p = dev.add_parser("check", help="print device info and save a screenshot")
    p.set_defaults(func=cmd_device_check)
    p = dev.add_parser("size", help="show, force or reset the 16:9 display override")
    p.add_argument("mode", nargs="?", choices=["show", "force", "reset"], default="show")
    p.set_defaults(func=cmd_size)

    p = sub.add_parser("run", help="run MaaEnd tasks by name, in order")
    p.add_argument("tasks", nargs="+")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("screenshot", help="save a screenshot")
    p.add_argument("--out", type=Path)
    p.set_defaults(func=cmd_screenshot)

    args = parser.parse_args(argv)
    return args.func(args)
