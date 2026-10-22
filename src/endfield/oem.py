"""Where each 情報檔案庫 page is obtained, from Open Endfieldmap (opendfieldmap.org/intel).

The intel page's script bundles, per page id, how it is acquired: a map pickup (with the
map marker's point id), a mission, automatically, an investigation, or a shop. Map
markers are published per area file (VL_* = 四號谷地, WL_* = 武陵). We name each area file
by its 繁中 name; the WL_* codes were matched to areas by marker position once (see
AREA_FILES) since the site's data names only VL_* areas.
"""

import json
import re
import urllib.request
from pathlib import Path

from endfield.vendor import VENDOR

SITE = "https://opendfieldmap.org/intel/"
DATA = "https://data.opendfieldmap.org"
CACHE = VENDOR.parent / "oem_intel.json"

AREA_FILES = {
    "VL_1": "樞紐區",
    "VL_2": "谷地通道",
    "VL_3": "阿伯莉採石場",
    "VL_5": "源石研究園",
    "VL_6": "礦脈源區",
    "VL_7": "供能高地",
    "WL_1": "景玉谷",
    "WL_2": "武陵城",
    "WL_3": "清波寨",
    "WL_4": "首墩",
    "WL_5": "實驗園區",
    "WL_6": "藏劍谷",
    "WL_7": "應龍關",
    "WL_8": "北部禁區",
    "WL_9": "雪松林",
    "WL_10": "祀的畫",
    "WL_16": "遂明",
    "DJ_1": "帝江號",
}
METHODS = {"map": "地圖拾取", "mission": "任務", "auto": "自動獲得", "invstgt": "調查", "shop": "商店"}
REGIONS = {"VL": "四號谷地", "WL": "武陵"}


def _get(url: str) -> bytes:
    # The data host refuses Python's default User-Agent.
    req = urllib.request.Request(url, headers={"User-Agent": "endfield/0.1 (+curl-compatible)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _acquisitions(bundle: str) -> dict[str, dict]:
    out = {}
    for m in re.finditer(r'\{"id":"(nar_[A-Za-z0-9_]+)","icon"', bundle):
        depth = 0
        for j in range(m.start(), len(bundle)):
            if bundle[j] == "{":
                depth += 1
            elif bundle[j] == "}":
                depth -= 1
                if depth == 0:
                    break
        out[m.group(1)] = json.loads(bundle[m.start() : j + 1]).get("acquisition", {})
    return out


def fetch() -> dict[str, str]:
    """page id -> 取得方式 text, e.g. "地圖拾取·景玉谷". Cached in vendor/."""
    html = _get(SITE).decode()
    acq: dict[str, dict] = {}
    for src in re.findall(r'src="(/intel/assets/intel-[A-Za-z0-9_-]+\.js)"', html):
        acq = _acquisitions(_get("https://opendfieldmap.org" + src).decode())
        if acq:
            break
    if not acq:
        raise RuntimeError("Open Endfieldmap intel page layout changed: no acquisition data")

    manifest_path = json.loads(_get(f"{DATA}/channels/stable.json"))["manifest"]["path"]
    manifest = json.loads(_get(DATA + manifest_path))
    area_of_point: dict[str, str] = {}
    for region in manifest["regions"]:
        for f in region["points"]:
            area = AREA_FILES.get(f["path"].rsplit("/", 1)[1].removesuffix(".json"), "")
            for p in json.loads(_get(DATA + f["path"])):
                area_of_point[str(p[0])] = area

    where = {}
    for page_id, a in acq.items():
        method = a.get("method", "")
        text = METHODS.get(method, method)
        if method == "map":
            area = area_of_point.get(str(a.get("pointId")), "")
            text += f"·{area}" if area else ""
        elif method == "shop":
            region = REGIONS.get(a.get("location", {}).get("regionId", ""), "")
            text += f"·{region}" if region else ""
        where[page_id] = text
    CACHE.write_text(json.dumps(where, ensure_ascii=False, indent=0), encoding="utf-8")
    return where


def load() -> dict[str, str]:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return fetch()
