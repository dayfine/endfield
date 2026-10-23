"""Owned-weapon scan: 貴重品庫 → 武器, sorted by 品質 descending.

Taps each card and reads the side panel (name, level, who has it equipped) with
MaaFramework's OCR, the same model MaaEnd uses. Read-only: it only taps cards and
scrolls the list. Stops once a whole screen holds no essence target.
"""

import difflib
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from endfield.vendor import VENDOR

WEAPON_DATA = VENDOR / "data" / "EssenceFilter" / "weapons_output.json"

# 1280x720 layout (force_size 720x1280).
GRID_X = [172, 301, 430, 559, 688, 817]
GRID_Y = [168, 297, 426, 555]
NAME_ROI = (905, 75, 220, 45)
LEVEL_ROI = (905, 310, 65, 45)
EQUIP_ROI = (960, 560, 200, 55)
HEADER_ROI = (95, 60, 200, 30)
SORT_ROI = (105, 625, 290, 45)
ESSENCE_ROI = (980, 262, 250, 36)
SKILLS_ROI = (905, 240, 330, 380)  # skill rows after PANEL_SCROLL
# Just enough to show the third skill. Start above the 裝備中 box, which eats drags.
PANEL_SCROLL = ((1070, 480), (1070, 340), 1000)
BAR_X = (915, 1070)
# Drag one row-step short of the visible height so each page overlaps the last.
SWIPE = ((500, 560), (500, 300), 1500)


@dataclass(frozen=True)
class Weapon:
    id: str
    name: str  # TC
    rarity: int
    level: int | None
    equipped_by: str | None
    read_name: str  # raw OCR, for checking matches
    essence: str | None = None  # essence pill text, e.g. 無瑕基質
    # per weapon skill, in panel order: (base, level, cap); essence share = level - base
    skills: tuple[tuple[int, int, int | None], ...] = ()


def load_catalog() -> dict[str, dict]:
    """TC name -> weapon record from MaaEnd's EssenceFilter data."""
    data = json.loads(WEAPON_DATA.read_text(encoding="utf-8"))
    return {w["names"]["TC"]: w for w in data.values()}


def match_name(read: str, catalog: dict[str, dict]) -> str | None:
    read = read.strip().strip("|").strip()
    if read in catalog:
        return read
    hits = difflib.get_close_matches(read, list(catalog), n=1, cutoff=0.6)
    return hits[0] if hits else None


def count_segments(image, name_box) -> tuple[int, int] | None:
    """Count white (base) and yellow (essence) segments in the bar under a skill name.

    `image` is BGR. The bar sits ~35px under the name's OCR box; take the row with the
    most segments in that band.
    """
    _, y, _, h = name_box
    best = None
    for row_y in range(y + h, min(y + h + 25, image.shape[0])):
        row = image[row_y, BAR_X[0]:BAR_X[1]].astype(int)
        b, g, r = row[:, 0], row[:, 1], row[:, 2]
        kind = ["Y" if (rr > 200 and gg > 170 and bb < 90) else "W" if min(bb, gg, rr) > 200 else "."
                for bb, gg, rr in zip(b, g, r)]
        runs = "".join(kind).split(".")
        white = sum(1 for x in runs if len(x) >= 4 and set(x) == {"W"})
        yellow = sum(1 for x in runs if len(x) >= 4 and set(x) == {"Y"})
        if best is None or white + yellow > sum(best):
            best = (white, yellow)
    return best if best and sum(best) else None


def parse_level(text: str) -> int | None:
    m = re.match(r"\D*(\d{1,2})", text)
    if not m:
        return None
    # Lv1 renders as a thin "1" next to "/90" and reads as 17 (seen on every Lv1 copy).
    return 1 if m.group(1) == "17" else int(m.group(1))


def parse_equipped(text: str) -> str | None:
    """Panel shows '<operator>' over '裝備中' when equipped."""
    for mark in ("裝備中", "装備中", "装备中", "裝备中"):
        if mark in text:
            name = text.replace(mark, "").strip()
            return name or "?"
    return None


class Scanner:
    def __init__(self, adb: str, serial: str, log_dir: Path):
        from maa.controller import AdbController
        from maa.resource import Resource
        from maa.tasker import Tasker
        from maa.toolkit import Toolkit

        Toolkit.init_option(str(log_dir))
        self.res = Resource()
        self.res.post_bundle(str(VENDOR / "resource")).wait()
        self.ctl = AdbController(adb, serial)
        if not self.ctl.post_connection().wait().succeeded:
            raise RuntimeError("MaaFramework could not connect to the device")
        self.tasker = Tasker()
        self.tasker.bind(self.res, self.ctl)
        if not self.tasker.inited:
            raise RuntimeError("MaaFramework tasker did not initialise")

    def screencap(self):
        return self.ctl.post_screencap().wait().get()

    def ocr_boxes(self, image, roi) -> list:
        from maa.pipeline import JOCR

        detail = self.tasker.post_recognition("OCR", JOCR(roi=roi), image).wait().get()
        reco = self.tasker.get_node_detail(detail.node_id_list[0]).recognition
        return sorted((r for r in reco.all_results if r.text), key=lambda r: (r.box[1], r.box[0]))

    def ocr(self, image, roi) -> str:
        return "".join(r.text for r in self.ocr_boxes(image, roi))

    def read_skills(self, image, roi) -> list[tuple[int, int, int]]:
        """Skill rows in panel order as (base, level, cap).

        A row is a name line with '·' that has a bar under it. White bar segments are
        the weapon's own levels; the level and cap come from the "a/b" text at the right
        (the MAX badge hides segments, so yellow is not counted directly).
        """
        boxes = self.ocr_boxes(image, roi)
        rows = []
        for r in boxes:
            if "·" not in r.text and "・" not in r.text:
                continue
            seg = count_segments(image, r.box)
            if not seg:
                continue
            white, yellow = seg
            level, cap = white + yellow, None
            for o in boxes:
                m = re.search(r"(\d)\s*/\s*(\d)", o.text)
                if m and o.box[0] > 1150 and abs(o.box[1] - (r.box[1] + 20)) < 20:
                    level, cap = int(m.group(1)), int(m.group(2))
                    break
            rows.append((white, level, cap))
        return rows[:3]

    def tap(self, x: int, y: int, settle: float = 0.6) -> None:
        self.ctl.post_click(x, y).wait()
        time.sleep(settle)

    def swipe(self) -> None:
        (x1, y1), (x2, y2), ms = SWIPE
        self.ctl.post_swipe(x1, y1, x2, y2, ms).wait()
        time.sleep(1.0)

    def check_start_screen(self) -> str | None:
        img = self.screencap()
        header, sort = self.ocr(img, HEADER_ROI), self.ocr(img, SORT_ROI)
        if "武器" not in header:
            return f"not on 貴重品庫 → 武器 (read {header!r})"
        if "品質" not in sort or "降序" not in sort:
            return f"list must be sorted 品質 / 降序 (read {sort!r})"
        return None

    def read_selected(self, catalog: dict[str, dict]) -> Weapon | None:
        img = self.screencap()
        read = self.ocr(img, NAME_ROI)
        name = match_name(read, catalog)
        if name is None:
            return Weapon("", "", 0, None, None, read) if read else None
        w = catalog[name]
        level = parse_level(self.ocr(img, LEVEL_ROI))
        equipped_by = parse_equipped(self.ocr(img, EQUIP_ROI))
        skills: list[tuple[int, int, int]] = []
        if _target(w["rarity"], level, equipped_by):
            # Scroll the panel a little so all three skill rows are on screen at once.
            (x1, y1), (x2, y2), ms = PANEL_SCROLL
            self.ctl.post_swipe(x1, y1, x2, y2, ms).wait()
            time.sleep(0.8)
            skills = self.read_skills(self.screencap(), SKILLS_ROI)
        return Weapon(
            id=w["internal_id"],
            name=name,
            rarity=w["rarity"],
            level=level,
            equipped_by=equipped_by,
            read_name=read,
            essence=self.ocr(img, ESSENCE_ROI) or None,
            skills=tuple(skills),
        )

    def to_top(self) -> None:
        for _ in range(12):
            self.ctl.post_swipe(500, 200, 500, 650, 150).wait()
        time.sleep(1.5)

    def scan(self, max_pages: int = 60) -> list[Weapon]:
        catalog = load_catalog()
        self.to_top()
        seen: list[Weapon] = []
        for page in range(max_pages):
            page_hits = 0
            for y in GRID_Y:
                for x in GRID_X:
                    self.tap(x, y)
                    w = self.read_selected(catalog)
                    if w is None:
                        continue
                    seen.append(w)
                    if _target(w.rarity, w.level, w.equipped_by) or not w.id:
                        page_hits += 1
                    print(f"  p{page} {w.name or '?' + w.read_name} {w.rarity}★ Lv{w.level} {w.equipped_by or ''} | {w.essence} {w.skills}", flush=True)
            if page_hits == 0:
                break
            self.swipe()
        return seen


def summarise(seen: list[Weapon]) -> list[dict]:
    """One row per weapon id: copies, best level, who has it equipped."""
    by_id: dict[str, dict] = {}
    for w in seen:
        if not w.id:
            continue
        row = by_id.setdefault(w.id, {"id": w.id, "name": w.name, "rarity": w.rarity,
                                      "max_level": 0, "equipped_by": [], "reads": 0,
                                      "copies": []})
        row["reads"] += 1
        if _target(w.rarity, w.level, w.equipped_by):
            copy = {"level": w.level, "equipped_by": w.equipped_by, "essence": w.essence,
                    "skills": [list(x) if x else None for x in w.skills]}
            if copy not in row["copies"]:
                row["copies"].append(copy)
        row["max_level"] = max(row["max_level"], w.level or 0)
        if w.equipped_by and w.equipped_by not in row["equipped_by"]:
            row["equipped_by"].append(w.equipped_by)
    return sorted(by_id.values(), key=lambda r: (-r["rarity"], -r["max_level"], r["name"]))


def _target(rarity: int, level: int | None, equipped_by) -> bool:
    """All 6★; 5★ only when equipped or leveled past 1 (config essence_targets)."""
    if rarity >= 6:
        return True
    return rarity == 5 and (bool(equipped_by) or (level or 0) > 1)


def is_target(row: dict) -> bool:
    return _target(row["rarity"], row["max_level"], row["equipped_by"])


def write(seen: list[Weapon], out: Path) -> Path:
    payload = {
        "raw": [asdict(w) for w in seen],
        "weapons": summarise(seen),
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
