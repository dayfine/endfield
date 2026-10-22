from dataclasses import dataclass
from pathlib import Path

import yaml

from endfield import ROOT


@dataclass(frozen=True)
class Config:
    adb: str
    serial: str
    package: str
    force_size: str | None
    client_version: str  # MaaEnd ClientVersion case: CN, Bilibili, Global, VN


def load(path: Path | None = None) -> Config:
    path = path or ROOT / "config.yaml"
    if not path.exists():
        raise SystemExit(f"missing {path}; copy config.example.yaml to config.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Config(
        adb=raw.get("adb", "adb"),
        serial=raw["serial"],
        package=raw.get("package", "com.gryphline.endfield.gp"),
        force_size=raw.get("force_size"),
        client_version=raw.get("client_version", "Global"),
    )
