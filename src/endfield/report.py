"""End-of-run report built from a run dir's maafw.log and go-service.log.

A task "Succeeded" in MaaEnd only means its pipeline reached an end node, not that it did
what we wanted (a credit shop that buys nothing still succeeds). The report lists what
each task actually did, as far as the logs show, and flags things that need a person.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

CREDIT_CAP = 300

_TS = rb"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\.\d+\]"
_TASK = re.compile(_TS + rb".*?msg=Tasker\.Task\.(Starting|Succeeded|Failed)\] \[details=\{\"entry\":\"([^\"]+)\"", re.M)
_NODE_OK = re.compile(_TS + rb".*?msg=Node\.PipelineNode\.Succeeded\].*?\"name\":\"([A-Za-z0-9_]+)\"", re.M)

# Nodes worth calling out when they ran: name -> note.
NOTABLE_NODES = {
    "StuckRepairAction": "OpenGame did not recognise the screen within 90s and force-restarted the game",
    "CreditShoppingBuyConfirm": "credit shop bought an item",
    "RefreshItem": "credit shop refreshed the shelf",
}


@dataclass
class TaskRun:
    entry: str
    start: datetime
    end: datetime | None = None
    ok: bool | None = None
    items: list[tuple[str, int]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def seconds(self) -> int | None:
        return int((self.end - self.start).total_seconds()) if self.end else None


def _ts(raw: bytes | str) -> datetime:
    return datetime.strptime(raw if isinstance(raw, str) else raw.decode(), "%Y-%m-%d %H:%M:%S")


def _agent_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("level") == "debug":
            continue
        d["_t"] = datetime.fromisoformat(d["time"]).replace(tzinfo=None) if "time" in d else None
        rows.append(d)
    return rows


def build(run_dir: Path) -> tuple[list[TaskRun], list[str]]:
    """Per-task runs and a list of problems for a person to look at."""
    log = (run_dir / "maafw.log").read_bytes()
    tasks: list[TaskRun] = []
    for ts, kind, entry in _TASK.findall(log):
        if kind == b"Starting":
            tasks.append(TaskRun(entry.decode(), _ts(ts)))
        elif tasks and tasks[-1].entry == entry.decode():
            tasks[-1].end, tasks[-1].ok = _ts(ts), kind == b"Succeeded"

    def task_at(t: datetime | None) -> TaskRun | None:
        for task in tasks:
            if t and task.start <= t and (task.end is None or t <= task.end):
                return task
        return None

    seen_nodes: set[tuple[str, str]] = set()
    for ts, name in _NODE_OK.findall(log):
        note = NOTABLE_NODES.get(name.decode())
        task = task_at(_ts(ts))
        if note and task and (task.entry, note) not in seen_nodes:
            seen_nodes.add((task.entry, note))
            task.notes.append(note)

    credits: int | None = None  # last on-screen reading, plus credits gained since
    picked: str | None = None  # stockpile goods named in the line before the buy decision
    warnings: dict[str, int] = {}
    for d in _agent_lines(run_dir / "go-service.log"):
        task, comp, msg = task_at(d["_t"]), d.get("component"), d.get("message", "")
        if comp == "AddItemData" and "item_name" in d and task:
            task.items.append((d["item_name"], d.get("delta", 0)))
            if d.get("item_id") == "item_spaceship_credit" and credits is not None:
                credits += d.get("delta", 0)
        elif comp == "ExpressionRecognition" and "CreditShoppingReserveCreditOCRInternal" in (d.get("values") or {}):
            credits = d["values"]["CreditShoppingReserveCreditOCRInternal"]
        elif comp == "autostockpile" and "product_name" in d and task:
            picked = d["product_name"]
        elif comp == "autostockpile" and "selection_mode" in d and task:
            task.notes.append(f"stockpile bought {picked or '?'} at {d.get('price')} (threshold {d.get('threshold')})")
        elif comp == "autostockpile" and d.get("overflow_detected") and task:
            task.notes.append(f"stockpile quota {d.get('overflow_current')}/{d.get('overflow_max')} (overflowing)")
        if d.get("level") in ("warn", "error"):
            key = f"{comp}: {msg}"
            warnings[key] = warnings.get(key, 0) + 1

    problems = []
    for task in tasks:
        if task.ok is False:
            problems.append(f"{task.entry} failed")
        elif task.ok is None:
            problems.append(f"{task.entry} never finished")
    if credits is not None and credits > CREDIT_CAP:
        problems.append(f"credits end at {credits}/{CREDIT_CAP}: {credits - CREDIT_CAP} above the cap get wiped")
    for task in tasks:
        if any("force-restarted" in n for n in task.notes):
            problems.append("OpenGame force-restarted the game (it was already open past the title screen)")
    if any(t.entry.startswith("CreditShopping") for t in tasks) and credits is None:
        problems.append("credit shop ran but no credit reading was logged")
    return tasks, problems + [f"warning x{n}: {k}" for k, n in sorted(warnings.items()) if n and _worth(k)]


def _worth(key: str) -> bool:
    # Known noise: sliders clamp to max by design; outpost plan printing is cosmetic.
    return not any(s in key for s in ("clamped to slider max", "failed to print outpost plan",
                                      "failed to bind price for goods"))


def render(run_dir: Path) -> str:
    tasks, problems = build(run_dir)
    lines = [f"# Run {run_dir.name}", ""]
    if problems:
        lines += ["## Needs attention", "", *[f"- {p}" for p in problems], ""]
    lines += ["## Tasks", "", "| Task | Start | Time | Result | Did |", "|---|---|---|---|---|"]
    for t in tasks:
        did = list(t.notes)
        gained: dict[str, int] = {}
        for name, n in t.items:
            gained[name] = gained.get(name, 0) + n
        if gained:
            did.append("got " + ", ".join(f"{n}× {name}" for name, n in gained.items()))
        secs = t.seconds
        result = {True: "ok", False: "FAILED", None: "unfinished"}[t.ok]
        time_s = f"{secs // 60}m{secs % 60:02d}s" if secs is not None else "?"
        lines.append(f"| {t.entry} | {t.start:%H:%M:%S} | {time_s} | {result} | {'; '.join(did)} |")
    shots = sorted((run_dir / "shots").glob("*.png")) if (run_dir / "shots").exists() else []
    if shots:
        lines += ["", f"Screenshots at each task end: {run_dir / 'shots'}"]
    return "\n".join(lines) + "\n"


def write(run_dir: Path) -> Path:
    out = run_dir / "summary.md"
    out.write_text(render(run_dir), encoding="utf-8")
    return out
