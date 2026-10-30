"""End-of-run report built from a run dir's maafw.log and go-service.log.

A task "Succeeded" in MaaEnd only means its pipeline reached an end node, not that it did
what we wanted (a credit shop that buys nothing still succeeds). The report lists what
each task actually did, as far as the logs show, and flags things that need a person.
"""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from functools import cache
from pathlib import Path

from endfield import pi
from endfield.vendor import VENDOR

CREDIT_CAP = 300

_TS = rb"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\.\d+\]"
_TASK = re.compile(_TS + rb".*?msg=Tasker\.Task\.(Starting|Succeeded|Failed)\] \[details=\{\"entry\":\"([^\"]+)\"", re.M)
_NODE_OK = re.compile(_TS + rb".*?msg=Node\.PipelineNode\.Succeeded\].*?\"name\":\"([A-Za-z0-9_]+)\"", re.M)

# Nodes worth calling out when they ran: name -> note.
NOTABLE_NODES = {
    "StuckRepairAction": "90 秒內未辨識畫面，已強制重啟遊戲",
    "CreditShoppingBuyConfirm": "信用商店有購買",
    "RefreshItem": "信用商店有刷新",
}


@dataclass
class TaskRun:
    entry: str
    start: datetime
    end: datetime | None = None
    ok: bool | None = None
    items: list[tuple[str, int]] = field(default_factory=list)  # (TC name, delta)
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
            task.items.append((item_label(d.get("item_id"), d["item_name"]), d.get("delta", 0)))
            if d.get("item_id") == "item_spaceship_credit" and credits is not None:
                credits += d.get("delta", 0)
        elif comp == "ExpressionRecognition" and "CreditShoppingReserveCreditOCRInternal" in (d.get("values") or {}):
            credits = d["values"]["CreditShoppingReserveCreditOCRInternal"]
        elif comp == "autostockpile" and "product_name" in d and task:
            picked = d["product_name"]
        elif comp == "autostockpile" and "selection_mode" in d and task:
            task.notes.append(f"囤貨買入 {picked or '?'}，價格 {d.get('price')}（門檻 {d.get('threshold')}）")
        elif comp == "autostockpile" and d.get("overflow_detected") and task:
            task.notes.append(f"囤貨配額 {d.get('overflow_current')}/{d.get('overflow_max')}（已滿）")
        if d.get("level") in ("warn", "error"):
            key = f"{comp}: {msg}"
            warnings[key] = warnings.get(key, 0) + 1

    problems = []
    for task in tasks:
        if task.ok is False:
            problems.append(f"{task_label(task.entry)} 失敗")
        elif task.ok is None:
            problems.append(f"{task_label(task.entry)} 未完成")
    if credits is not None and credits > CREDIT_CAP:
        problems.append(f"信用結束時 {credits}/{CREDIT_CAP}：超出上限的 {credits - CREDIT_CAP} 會被清空")
    for task in tasks:
        if any("強制重啟" in n for n in task.notes):
            problems.append("打開遊戲時強制重啟了遊戲（遊戲原本已在標題畫面之後）")
    if any(t.entry.startswith("CreditShopping") for t in tasks) and credits is None:
        problems.append("信用商店有執行，但日誌沒有讀到信用數量")
    return tasks, problems + [f"警告 x{n}：{k}" for k, n in sorted(warnings.items()) if n and _worth(k)]


def _worth(key: str) -> bool:
    # Known noise: sliders clamp to max by design; outpost plan printing is cosmetic.
    return not any(s in key for s in ("clamped to slider max", "failed to print outpost plan",
                                      "failed to bind price for goods"))


@cache
def _labels() -> tuple[dict[str, str], dict[str, str]]:
    """Pipeline entry -> TC task label, and item id -> TC item name, from MaaEnd's locale."""
    loc = json.loads((VENDOR / "locales" / "interface" / "zh_tw.json").read_text(encoding="utf-8"))
    tasks = {}
    for t in pi._task_defs().values():
        label = loc.get(t.get("label", "").removeprefix("$"), "")
        # Drop the leading emoji: terminals disagree on its width, which breaks the table.
        label = label.lstrip("".join(c for c in label if unicodedata.category(c) == "So" or c == "\ufe0f"))
        if label:
            tasks.setdefault(t["entry"], label)
    items = {k.removeprefix("iconRecognition.name."): v for k, v in loc.items()
             if k.startswith("iconRecognition.name.")}
    return tasks, items


def task_label(entry: str) -> str:
    try:
        return _labels()[0].get(entry, entry)
    except (OSError, ValueError):  # no vendor bundle (tests): keep the entry name
        return entry


def item_label(item_id: str | None, name: str) -> str:
    try:
        return _labels()[1].get(item_id or "", name)
    except (OSError, ValueError):
        return name


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def table(header: list[str], rows: list[list[str]]) -> list[str]:
    """Markdown table padded by display width (CJK counts double) so it also lines up as
    plain text in a terminal. The last column isn't padded: it holds the long notes."""
    cols = list(zip(header, *rows))
    widths = [max(map(_width, c)) for c in cols[:-1]] + [0]

    def line(cells: list[str]) -> str:
        return "| " + " | ".join(c + " " * (w - _width(c)) for c, w in zip(cells, widths)) + " |"
    return [line(header), line(["-" * max(w, 3) for w in widths]), *map(line, rows)]


def render(run_dir: Path) -> str:
    tasks, problems = build(run_dir)
    lines = [f"# 執行紀錄 {run_dir.name}", ""]
    if problems:
        lines += ["## 需要處理", "", *[f"- {p}" for p in problems], ""]
    rows = []
    for t in tasks:
        did = list(t.notes)
        gained: dict[str, int] = {}
        for name, n in t.items:
            gained[name] = gained.get(name, 0) + n
        if gained:
            did.append("獲得 " + "、".join(f"{name}×{n}" for name, n in gained.items()))
        secs = t.seconds
        result = {True: "成功", False: "失敗", None: "未完成"}[t.ok]
        time_s = f"{secs // 60}分{secs % 60:02d}秒" if secs is not None else "?"
        rows.append([task_label(t.entry), f"{t.start:%H:%M:%S}", time_s, result, "；".join(did)])
    lines += ["## 任務", "", *table(["任務", "開始", "耗時", "結果", "內容"], rows)]
    shots = sorted((run_dir / "shots").glob("*.png")) if (run_dir / "shots").exists() else []
    if shots:
        lines += ["", f"每個任務結束時的截圖：{run_dir / 'shots'}"]
    return "\n".join(lines) + "\n"


def write(run_dir: Path) -> Path:
    out = run_dir / "summary.md"
    out.write_text(render(run_dir), encoding="utf-8")
    return out
