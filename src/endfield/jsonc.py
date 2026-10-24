"""Load JSON with // and /* */ comments and trailing commas (as MaaFramework accepts)."""

import json
from pathlib import Path


def strip(text: str) -> str:
    out: list[str] = []
    i, n, in_str = 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\":
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end
            continue
        elif text.startswith("/*", i):
            i = text.index("*/", i) + 2
            continue
        else:
            if c in "}]":
                _drop_trailing_comma(out)
            out.append(c)
        i += 1
    return "".join(out)


def _drop_trailing_comma(out: list[str]) -> None:
    j = len(out) - 1
    while j >= 0 and out[j].isspace():
        j -= 1
    if j >= 0 and out[j] == ",":
        del out[j]


def loads(text: str):
    return json.loads(strip(text))


def load(path: Path):
    return loads(path.read_text(encoding="utf-8"))
