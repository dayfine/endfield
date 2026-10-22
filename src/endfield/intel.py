"""情報檔案庫 collection table, from a MaaEnd IntelArchive run.

IntelArchive ends by building an Open Endfieldmap import URL whose payload (gzip + base64)
lists collected and not-collected page ids. We join those ids with MaaEnd's catalog
(data/IntelArchive/items.json) into one row per archive page.
"""

import base64
import csv
import difflib
import gzip
import json
import re
from dataclasses import dataclass
from pathlib import Path

from endfield.vendor import VENDOR

SECTIONS = {
    "investigate": "情報採集",
    "multi_media": "音像存檔",
    "text": "見聞輯錄",
    "document": "中樞檔案",
}
CATEGORIES = {
    "investigate": "事件調查",
    "media": "多媒體",
    "paper": "紙本紀錄",
    "digital": "電子檔案",
    "collection": "藏品",
    "document": "中樞檔案",
    "report": "調查報告",
}
REGIONS = {"map01": "四號谷地", "map02": "武陵"}
_REGION = re.compile(r"map0\d")


@dataclass
class Row:
    page_id: str
    section: str
    category: str
    item: str
    page: str
    region: str
    investigation: str
    collected: bool
    source: str = ""  # "" when MaaEnd matched it, "ocr-fuzzy" when recovered by us


def payload_from_log(go_service_log: Path) -> dict:
    """The last import payload IntelArchive logged."""
    url = None
    for line in go_service_log.read_text(encoding="utf-8", errors="replace").splitlines():
        if '"intel import url built"' in line:
            url = json.loads(line)["url"]
    if url is None:
        raise ValueError(f"no IntelArchive import URL in {go_service_log}")
    return decode_url(url)


def misses_from_log(go_service_log: Path) -> list[tuple[str, str]]:
    """(ocr text, file category) for each card title MaaEnd couldn't find in its catalog."""
    out = []
    for line in go_service_log.read_text(encoding="utf-8", errors="replace").splitlines():
        if '"catalog lookup miss"' in line:
            d = json.loads(line)
            out.append((d.get("ocr", ""), d.get("file_category", "")))
    return out


_TRUNC = re.compile(r"(\.{2,}|…+)$")
_HAN = re.compile(r"[\u4e00-\u9fff]")


def fuzzy_match(ocr: str, names: list[str], cutoff: float = 0.75) -> str | None:
    """The one catalog name an OCR'd card title most likely is, or None.

    Card titles that don't fit end in "…"; those match by prefix. Others match by
    similarity. Ambiguous or noisy text (no Chinese characters) gives None.
    """
    if len(_HAN.findall(ocr)) < 2:
        return None
    trunc = _TRUNC.search(ocr)
    if trunc:
        prefix = ocr[: trunc.start()]
        hits = [n for n in names if n.startswith(prefix)]
        if len(hits) == 1:
            return hits[0]
        if hits:
            return None
        ocr = prefix
    scored = sorted(
        ((difflib.SequenceMatcher(None, ocr, n[: len(ocr)] if trunc else n).ratio(), n) for n in names),
        reverse=True,
    )
    if not scored or scored[0][0] < cutoff:
        return None
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None
    return scored[0][1]


def decode_url(url: str) -> dict:
    # https://oem.re/i/MAE-<version>-<base64url(gzip(json))>
    data = url.rsplit("/", 1)[1].split("-", 2)[2]
    raw = gzip.decompress(base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)))
    return json.loads(raw)


def rows(
    payload: dict,
    misses: list[tuple[str, str]] = (),
    items_path: Path = VENDOR / "data/IntelArchive/items.json",
) -> list[Row]:
    items = json.loads(items_path.read_text(encoding="utf-8"))["items"]
    lists = payload["data"]["prtsAllItems"]
    collected = set(lists["collected"])

    by_category: dict[str, dict[str, dict]] = {}
    for it in items.values():
        by_category.setdefault(it["fileCategory"], {})[it["names"]["zh_tw"]] = it
    fuzzy: set[str] = set()
    for ocr, category in misses:
        names = by_category.get(category, {})
        name = fuzzy_match(ocr, list(names))
        if name:
            fuzzy.update(p["id"] for p in names[name].get("pages", []))
    fuzzy -= collected

    investigation_of: dict[str, str] = {}
    for it in items.values():
        for g in it.get("groups", []):
            for e in g.get("entries", []):
                investigation_of[e["pageId"]] = it["names"]["zh_tw"]

    out = []
    for it in sorted(items.values(), key=lambda i: (i["page"], i.get("order", 0), i["id"])):
        multi = len(it.get("pages", [])) > 1
        region = _REGION.search(it["id"])
        for p in it.get("pages", []):
            out.append(
                Row(
                    page_id=p["id"],
                    section=SECTIONS.get(it["page"], it["page"]),
                    category=CATEGORIES.get(it["fileCategory"], it["fileCategory"]),
                    item=it["names"]["zh_tw"],
                    page=p["names"]["zh_tw"] if multi else "",
                    region=REGIONS.get(region[0], region[0]) if region else "",
                    investigation=investigation_of.get(p["id"], ""),
                    collected=p["id"] in collected or p["id"] in fuzzy,
                    source="ocr-fuzzy" if p["id"] in fuzzy else "",
                )
            )
    return out


def write_csv(table: list[Row], path: Path) -> Path:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["page_id", "分區", "類別", "名稱", "頁", "地區", "所屬調查", "已收集", "來源"])
        for r in table:
            w.writerow([
                r.page_id, r.section, r.category, r.item, r.page, r.region, r.investigation,
                "✓" if r.collected else "", "OCR近似" if r.source else "",
            ])
    return path
