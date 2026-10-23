import argparse
import datetime as dt
from pathlib import Path

from endfield import ROOT, config, intel, oem, pi, vendor, weapons
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


def _opt(value):
    """YAML option value -> MaaPiCli value (case names and inputs are strings)."""
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, dict):
        return {k: str(v) for k, v in value.items()}
    return str(value)


def cmd_run(args: argparse.Namespace) -> int:
    cfg = config.load()
    dev = Device(cfg)
    if not dev.is_connected():
        print(f"device {cfg.serial} not connected")
        return 1
    if args.preset:
        entries = cfg.presets.get(args.preset)
        if entries is None:
            print(f"no preset {args.preset!r} in config.yaml")
            return 1
        tasks = [pi.Task(e["task"], {k: _opt(v) for k, v in (e.get("options") or {}).items()}) for e in entries]
    else:
        tasks = [pi.Task(name) for name in args.tasks]
    if args.only:
        tasks = [t for t in tasks if t.name in args.only]
        if not tasks:
            print(f"none of {args.only} in the task list")
            return 1
    for task in tasks:
        if task.name in ("AndroidOpenGame", "CloseGame"):
            task.options["ClientVersion"] = cfg.client_version
    problems = pi.validate(tasks)
    if problems:
        print("config problems:\n  " + "\n  ".join(problems))
        return 1
    if args.dry_run:
        for t in tasks:
            print(t.name, t.options or "")
        return 0
    dev.shell("input keyevent KEYCODE_WAKEUP")
    if dev.is_locked():
        print("phone is locked: unlock it, then run again")
        return 2
    run_dir = _run_dir()
    with dev.stay_awake(), dev.forced_size():
        ok = pi.run(cfg, tasks, run_dir)
        if not ok:
            dev.screenshot(run_dir / "failure.png")
    print(f"{'ok' if ok else 'failed'}: logs in {run_dir}")
    return 0 if ok else 1


def cmd_intel(args: argparse.Namespace) -> int:
    if not args.no_run:
        code = cmd_run(argparse.Namespace(tasks=["IntelArchive"], preset=None, only=None, dry_run=False))
        if code != 0:
            return code
    run_dir = sorted((ROOT / "runs").iterdir())[-1]
    log = run_dir / "go-service.log"
    if not log.exists():
        log = pi.PI_DIR / "debug" / "go-service.log"
    try:
        where = oem.load()
    except OSError as e:  # the table is still useful without it
        print(f"Open Endfieldmap unavailable ({e}); 取得方式 left empty")
        where = {}
    payload = intel.remember(intel.payload_from_log(log))
    table = intel.rows(payload, intel.misses_from_log(log), where)
    out = intel.write_csv(table, run_dir / "intel.csv")
    done = sum(r.collected for r in table)
    print(f"{done}/{len(table)} collected; table in {out}")
    return 0


def cmd_weapons(args: argparse.Namespace) -> int:
    cfg = config.load()
    dev = Device(cfg)
    if not dev.is_connected():
        print(f"device {cfg.serial} not connected")
        return 1
    dev.shell("input keyevent KEYCODE_WAKEUP")
    if dev.is_locked():
        print("phone is locked: unlock it, then run again")
        return 2
    run_dir = _run_dir()
    with dev.stay_awake(), dev.forced_size():
        scanner = weapons.Scanner(cfg.adb, cfg.serial, run_dir / "maa")
        problem = scanner.check_start_screen()
        if problem:
            print(f"{problem}; open 貴重品庫 → 武器, sort by 品質 / 降序, then run again")
            return 1
        seen = scanner.scan()
    out = weapons.write(seen, run_dir / "weapons.json")
    rows = weapons.summarise(seen)
    targets = [r for r in rows if weapons.is_target(r)]
    unread = sum(1 for w in seen if not w.id)
    print(f"{len(rows)} distinct weapons read, {len(targets)} targets, {unread} unmatched names; {out}")
    return 0


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

    p = sub.add_parser("run", help="run MaaEnd tasks by name, or a preset from config.yaml")
    p.add_argument("tasks", nargs="*")
    p.add_argument("--preset", help="preset name in config.yaml, e.g. daily")
    p.add_argument("--only", nargs="+", metavar="TASK", help="run only these tasks of the list")
    p.add_argument("--dry-run", action="store_true", help="validate and print, don't run")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("intel", help="scan 情報檔案庫 and write a collection table (CSV)")
    p.add_argument("--no-run", action="store_true", help="only rebuild from the last run")
    p.set_defaults(func=cmd_intel)

    p = sub.add_parser("weapons", help="scan owned weapons (貴重品庫 → 武器) into weapons.json")
    p.set_defaults(func=cmd_weapons)

    p = sub.add_parser("screenshot", help="save a screenshot")
    p.add_argument("--out", type=Path)
    p.set_defaults(func=cmd_screenshot)

    args = parser.parse_args(argv)
    return args.func(args)
