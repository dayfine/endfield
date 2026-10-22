"""Generated resource layer that adds Traditional Chinese text to MaaEnd's OCR nodes.

Most MaaEnd OCR nodes already list zh_cn, zh_tw, en and ja text, but some only have
Simplified Chinese. For those we write an override node whose `expected` list also has
the OpenCC conversions (s2t and Taiwan phrasing s2twp). The layer is loaded after
MaaEnd's own (resource, then resource_adb), and same-name nodes override earlier ones.
"""

import copy
import json
import re
from pathlib import Path

from opencc import OpenCC

from endfield import jsonc
from endfield.vendor import VENDOR

LAYER = VENDOR.parent / "endfield_tc"
BASE_LAYERS = ["resource", "resource_adb"]

_HAN = re.compile(r"[一-鿿]")
_CONVERTERS = [OpenCC("s2t"), OpenCC("s2twp")]

# Traditional characters MaaEnd's OCR model (mostly trained on Simplified) reads as
# another character on the TC client. Seen on device: 節點一覽 read as 節点一覽.
OCR_CONFUSIONS = {"點": "点"}


def merged_nodes(root: Path = VENDOR) -> dict:
    nodes: dict = {}
    for layer in BASE_LAYERS:
        for path in sorted((root / layer / "pipeline").rglob("*.json")):
            for name, node in jsonc.load(path).items():
                if isinstance(node, dict):
                    nodes[name] = {**nodes.get(name, {}), **node}
    return nodes


def tc_variants(text: str) -> list[str]:
    return [v for v in dict.fromkeys(c.convert(text) for c in _CONVERTERS) if v != text]


def _confused(text: str) -> str:
    return "".join(OCR_CONFUSIONS.get(ch, ch) for ch in text)


def _with_tc(exp) -> list[str] | None:
    exp = [exp] if isinstance(exp, str) else list(exp)
    new = list(exp)
    for e in exp:
        if not _HAN.search(e):
            continue
        for v in [*tc_variants(e), e]:
            for w in (v, _confused(v)):
                if w not in new:
                    new.append(w)
    return new if len(new) > len(exp) else None


def _patch(reco_holder: dict) -> bool:
    """Add TC text in place to one recognition holder (a node or an inline sub-recognition)
    and to any inline sub-recognitions under And/Or. Returns whether anything changed."""
    changed = False
    reco = reco_holder.get("recognition")
    if isinstance(reco, dict):
        rtype, param = reco.get("type"), reco.get("param", {})
    else:
        rtype, param = reco, reco_holder
    if rtype == "OCR" and param.get("expected"):
        new = _with_tc(param["expected"])
        if new:
            param["expected"] = new
            changed = True
    elif rtype in ("And", "Or"):
        for key in ("all_of", "any_of"):
            for sub in param.get(key) or []:
                if isinstance(sub, dict):
                    changed |= _patch(sub)
    return changed


# Keys of a node that can hold recognition settings.
_RECO_KEYS = ("recognition", "expected", "all_of", "any_of")


def tc_override(node: dict) -> dict | None:
    """Override for one node, or None if it needs none.

    Gives each changed recognition key whole, so the result is the same whether the
    framework merges nested fields or replaces them.
    """
    new = copy.deepcopy(node)
    if not _patch(new):
        return None
    return {k: new[k] for k in _RECO_KEYS if k in new and new[k] != node.get(k)}


def build(root: Path = VENDOR, out: Path = LAYER) -> int:
    overrides = {}
    for name, node in merged_nodes(root).items():
        o = tc_override(node)
        if o:
            overrides[name] = o
    pipeline = out / "pipeline"
    pipeline.mkdir(parents=True, exist_ok=True)
    (pipeline / "tc_ocr.json").write_text(
        json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return len(overrides)
