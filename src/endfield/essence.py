"""Essence farming: progress toward the weapons we want, a farming plan, and a task that
takes the player to a 重度能量淤積點 with 預刻寫 set, stopping before the challenge.

預刻寫 = 3 base attributes (slot 1) + 1 locked slot-2 or slot-3 skill that the location
offers. A drop then matches one weapon fully with odds about 1/3 x 1/(other slot's pool).
"""

import itertools
import json
from dataclasses import dataclass
from pathlib import Path

from endfield import ROOT, jsonc, pi
from endfield.vendor import VENDOR

DATA = VENDOR / "data" / "EssenceFilter"
LOCATION_DIR = VENDOR / "tasks" / "AutoEssence" / "Location"
LOCALE = VENDOR / "locales" / "interface" / "zh_tw.json"
# Resource layer for `essence go`: never claims, discards or starts the challenge.
STOP_LAYER = ROOT / "resources" / "essence_go"


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


def unreachable(names: list[str], steps: list[Step]) -> list[str]:
    covered = {w for s in steps for w in s.weapons}
    return [n for n in names if n not in covered]


def latest_scan() -> Path | None:
    scans = sorted((ROOT / "runs").glob("*/weapons.json"))
    return scans[-1] if scans else None


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


def go_task(step: Step) -> pi.Task:
    """AutoEssence in Location mode; with STOP_LAYER it ends on the 開啟挑戰 screen."""
    return pi.Task("AutoEssence", {
        "AutoEssenceSchedule": [f"AutoEssenceSchedule{d}" for d in
                                ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")],
        "AutoEssenceMenu": "Location",
        "AutoEssenceSelectLocation": step.location,
        "AutoEssenceLocationSlot1": fill_base(step.base),
        f"AutoEssenceLocationSecondary_{step.location}": step.lock,
        "AutoEssenceObtainModeClaimOnly": "ObtainScaling1",
        "AutoEssenceDoOverride": "No",
        "AutoUseSpMedication": "EndTask",
        "EssenceFilterAfterBattle": "No",
        "AutoEssenceRepeatCount": {"AutoEssenceRepeatCountValue": "1"},
    })


def describe(step: Step) -> str:
    locs = locations()
    base = "/".join(skill_label(c) for c in fill_base(step.base))
    return (f"{locs[step.location]['name']}  基礎={base}  鎖={skill_label(step.lock)}"
            f"  -> {', '.join(step.weapons)}  (~1/{round(1 / step.odds)} per drop)")
