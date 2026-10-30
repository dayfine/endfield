"""Essence farming: progress toward the weapons we want, a farming plan, and a task that
takes the player to a 重度能量淤積點 with 預刻寫 set, stopping before the challenge.

預刻寫 = 3 base attributes (slot 1) + 1 locked slot-2 or slot-3 skill that the location
offers. A drop then matches one weapon fully with odds about 1/3 x 1/(other slot's pool).
"""

import dataclasses
import itertools
import json
from dataclasses import dataclass
from pathlib import Path

from endfield import ROOT, jsonc, pi
from endfield.vendor import VENDOR

DATA = VENDOR / "data" / "EssenceFilter"
LOCATION_DIR = VENDOR / "tasks" / "AutoEssence" / "Location"
LOCALE = VENDOR / "locales" / "interface" / "zh_tw.json"
# Phone-layout fixes both commands load first.
COMMON_LAYER = ROOT / "resources" / "essence_common"
# Resource layer for `essence go`: never claims, discards or starts the challenge.
STOP_LAYER = ROOT / "resources" / "essence_go"
# Resource layer for `essence scan`: EssenceFilter export that doesn't abort on TC OCR.
SCAN_LAYER = ROOT / "resources" / "essence_scan"
# Resource layer for `essence farm`: one round (run off, wait, claim), ends on the loot screen.
FARM_LAYER = ROOT / "resources" / "essence_farm"
# The last plan `essence plan` printed; later plans only remove weapons from it.
PLAN_FILE = ROOT / "runs" / "essence_plan.json"


def _locale() -> dict[str, str]:
    return json.loads(LOCALE.read_text(encoding="utf-8"))


def locations() -> dict[str, dict]:
    """AutoEssence location case -> {"name": TC name, "secondary": {code: TC label}}."""
    loc = _locale()
    out = {}
    for case in jsonc.load(LOCATION_DIR / "SelectLocation.json")["option"]["AutoEssenceSelectLocation"]["cases"]:
        name = case["name"]
        opt = jsonc.load(LOCATION_DIR / f"{name}.json")["option"][f"AutoEssenceLocationSecondary_{name}"]
        out[name] = {
            "name": loc[case["label"].removeprefix("$")],
            "secondary": {c["name"]: skill_label(c["name"]) for c in opt["cases"]},
        }
    return out


def skill_label(code: str) -> str:
    return _locale()[f"option.AutoEssenceSkill.{code}"].removesuffix("提升")


def _codes(slot: int, text: str) -> str:
    """Weapon skill text (e.g. '敏捷提升·大') -> AutoEssence code (e.g. 's1_4')."""
    pools = json.loads((DATA / "skill_pools.json").read_text(encoding="utf-8"))[f"slot{slot}"]
    best = max((p for p in pools if text.startswith(p["tc"])), key=lambda p: len(p["tc"]), default=None)
    if best is None:
        raise ValueError(f"no slot {slot} skill matches {text!r}")
    return f"s{slot}_{best['id']}"


def needs(names: list[str]) -> dict[str, tuple[str, str, str]]:
    """Weapon TC name -> its three skill codes."""
    cat = {w["names"]["TC"]: w for w in json.loads((DATA / "weapons_output.json").read_text(encoding="utf-8")).values()}
    missing = [n for n in names if n not in cat]
    if missing:
        raise SystemExit(f"unknown weapons in essence_farm: {missing}")
    return {n: tuple(_codes(i + 1, s) for i, s in enumerate(cat[n]["skills"]["TC"])) for n in names}


@dataclass(frozen=True)
class Step:
    location: str  # case name, e.g. VFTheHub
    base: tuple[str, ...]  # 3 slot-1 codes (fewer when any works)
    lock: str  # s2_* or s3_*
    weapons: tuple[str, ...]
    odds: float  # chance per drop of a perfect essence for one of `weapons`


def plan(names: list[str]) -> list[Step]:
    """Greedy cover: repeatedly pick the 預刻寫 that serves most remaining weapons."""
    need, locs = needs(names), locations()
    options = []
    for case, info in locs.items():
        sec = set(info["secondary"])
        s2, s3 = {c for c in sec if c.startswith("s2_")}, {c for c in sec if c.startswith("s3_")}
        # Sorted so ties break the same way every time: `essence go N` must match `plan`.
        for lock in sorted(sec, key=lambda c: (c[:2], int(c[3:]))):
            other = len(s3) if lock.startswith("s2_") else len(s2)
            fits = {n: v for n, v in need.items()
                    if v[1] in s2 and v[2] in s3 and lock in (v[1], v[2])}
            for base in itertools.combinations([f"s1_{i}" for i in range(1, 6)], 3):
                hit = tuple(n for n, v in fits.items() if v[0] in base)
                if hit:
                    options.append(Step(case, base, lock, hit, len(hit) / 3 / other))
    steps, left = [], set(names)
    while left:
        best = max(options, key=lambda s: (len(set(s.weapons) & left), s.odds), default=None)
        if best is None or not set(best.weapons) & left:
            break
        served = tuple(w for w in best.weapons if w in left)
        # Only the base attributes the served weapons use matter; fill the rest freely.
        used = sorted({need[w][0] for w in served})
        steps.append(Step(best.location, tuple(used), best.lock, served, best.odds))
        left -= set(served)
    return steps


def carry_over(prev: list[Step], names: list[str]) -> list[Step]:
    """The previous plan minus weapons no longer needed, so a new plan is a subset of the
    last one: steps keep their 預刻寫 and order, and only drop out once empty. Needed
    weapons the old plan didn't cover (newly added to essence_farm) are planned after it."""
    left, steps = set(names), []
    for s in prev:
        served = tuple(w for w in s.weapons if w in left)
        if served:
            steps.append(Step(s.location, s.base, s.lock, served, s.odds * len(served) / len(s.weapons)))
            left -= set(served)
    extra = [n for n in names if n in left]
    return steps + (plan(extra) if extra else [])


def load_plan(path: Path = PLAN_FILE) -> list[Step] | None:
    if not path.exists():
        return None
    return [Step(s["location"], tuple(s["base"]), s["lock"], tuple(s["weapons"]), s["odds"])
            for s in json.loads(path.read_text(encoding="utf-8"))]


def save_plan(steps: list[Step], path: Path = PLAN_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([dataclasses.asdict(s) for s in steps], ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")


def unreachable(names: list[str], steps: list[Step]) -> list[str]:
    covered = {w for s in steps for w in s.weapons}
    return [n for n in names if n not in covered]


def latest_scan() -> Path | None:
    scans = sorted((ROOT / "runs").glob("*/weapons.json"))
    return scans[-1] if scans else None


def latest_export() -> Path | None:
    exports = sorted((ROOT / "runs").glob("*/EssenceInventory.json"))
    return exports[-1] if exports else None


def owned(export: Path | None) -> dict[str, list[tuple[int, ...]]]:
    """Weapon TC name -> levels of each 無瑕基質 we hold whose three skills match it fully,
    from an `essence scan` export (groups of {weapon_ids, essences: [{levels, count}]})."""
    if export is None:
        return {}
    cat = json.loads((DATA / "weapons_output.json").read_text(encoding="utf-8"))
    out: dict[str, list[tuple[int, ...]]] = {}
    for group in json.loads(export.read_text(encoding="utf-8")):
        levels = [tuple(e["levels"]) for e in group["essences"] for _ in range(e.get("count", 1))]
        for wid in group["weapon_ids"]:
            name = cat[wid]["names"]["TC"] if wid in cat else wid
            out.setdefault(name, []).extend(levels)
    for v in out.values():
        v.sort(reverse=True)
    return out


def still_needed(names: list[str], have: dict[str, list]) -> list[str]:
    """Weapons we hold no matching 無瑕基質 for yet: the ones worth farming."""
    return [n for n in names if not have.get(n)]


def progress(names: list[str], scan: Path | None) -> dict[str, str]:
    """Weapon -> "gap" text from the latest weapon scan (levels still missing per skill)."""
    rows = {}
    if scan:
        rows = {w["name"]: w for w in json.loads(scan.read_text(encoding="utf-8"))["weapons"]}
    out = {}
    for n in names:
        copies = (rows.get(n) or {}).get("copies") or []
        best = None
        for c in copies:
            skills = [s for s in c.get("skills") or [] if s]
            if len(skills) == 3 and all(s[2] for s in skills):
                gap = sum(s[2] - s[1] for s in skills)
                if best is None or gap < best[0]:
                    best = (gap, c.get("essence"), skills)
        if best is None:
            out[n] = "not in scan"
        elif best[0] == 0:
            out[n] = "done (all skills at cap)"
        else:
            out[n] = f"{best[1] or '?'}, {best[0]} levels short ({' '.join(f'{s[1]}/{s[2]}' for s in best[2])})"
    return out


def fill_base(base: tuple[str, ...]) -> list[str]:
    """預刻寫 always takes exactly 3 base attributes."""
    out = list(base)
    for code in ("s1_1", "s1_2", "s1_3", "s1_4", "s1_5"):
        if len(out) == 3:
            break
        if code not in out:
            out.append(code)
    return out


def go_task(step: Step, claim: bool = False) -> pi.Task:
    """AutoEssence in Location mode. With STOP_LAYER it ends on the 開啟挑戰 screen; with
    FARM_LAYER and claim=True it claims at single scaling using a 刻寫券 (80 理智), never
    using 理智 medicine."""
    return pi.Task("AutoEssence", {
        "AutoEssenceSchedule": [f"AutoEssenceSchedule{d}" for d in
                                ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")],
        "AutoEssenceMenu": "Location",
        "AutoEssenceSelectLocation": step.location,
        "AutoEssenceLocationSlot1": fill_base(step.base),
        f"AutoEssenceLocationSecondary_{step.location}": step.lock,
        "AutoEssenceObtainModeClaimOnly": "ObtainScaling1",
        "AutoEssenceDoOverride": "Yes" if claim else "No",
        "AutoUseSpMedication": "EndTask",
        "EssenceFilterAfterBattle": "No",
        "AutoEssenceRepeatCount": {"AutoEssenceRepeatCountValue": "1"},
    })


def describe(step: Step) -> str:
    locs = locations()
    base = "/".join(skill_label(c) for c in fill_base(step.base))
    return (f"{locs[step.location]['name']}  基礎={base}  鎖={skill_label(step.lock)}"
            f"  -> {', '.join(step.weapons)}  (~1/{round(1 / step.odds)} per drop)")


def scan_task() -> pi.Task:
    """MaaEnd's EssenceFilter inventory export: read-only, no marks changed."""
    return pi.Task("EssenceFilter", {"ExportInventory": "Yes"})


def find_export(since: float) -> Path | None:
    """EssenceInventory.json written by the agent after `since` (epoch seconds)."""
    hits = [p for p in (pi.PI_DIR).rglob("EssenceInventory*.json") if p.stat().st_mtime >= since]
    return max(hits, key=lambda p: p.stat().st_mtime) if hits else None
