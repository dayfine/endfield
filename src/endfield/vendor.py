"""Fetch the pinned MaaEnd release bundle into vendor/maaend (see maaend.lock)."""

import hashlib
import json
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from endfield import ROOT

LOCK = ROOT / "maaend.lock"
VENDOR = ROOT / "vendor" / "maaend"
STAMP = VENDOR / ".maaend-version"
PICLI = VENDOR / "maafw" / "MaaPiCli"


def lock() -> dict:
    return json.loads(LOCK.read_text(encoding="utf-8"))


def installed_version() -> str | None:
    return STAMP.read_text().strip() if STAMP.exists() else None


def _download(url: str, dest: Path, sha256: str) -> None:
    h = hashlib.sha256()
    with urllib.request.urlopen(url) as resp, dest.open("wb") as out:
        while chunk := resp.read(1 << 20):
            h.update(chunk)
            out.write(chunk)
    if h.hexdigest() != sha256:
        raise SystemExit(f"sha256 mismatch for {url}: got {h.hexdigest()}")


def fetch(force: bool = False) -> Path:
    want = lock()
    if not force and installed_version() == want["version"]:
        print(f"MaaEnd {want['version']} already in {VENDOR}")
        return VENDOR
    with tempfile.TemporaryDirectory() as tmp:
        dmg = Path(tmp) / want["asset"]
        print(f"downloading {want['url']}")
        _download(want["url"], dmg, want["sha256"])
        mnt = Path(tmp) / "mnt"
        subprocess.run(
            ["hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", mnt, dmg],
            check=True,
            capture_output=True,
        )
        try:
            if VENDOR.exists():
                shutil.rmtree(VENDOR)
            shutil.copytree(mnt / "MaaEnd.app" / "Contents" / "MacOS", VENDOR, symlinks=True)
        finally:
            subprocess.run(["hdiutil", "detach", mnt], check=True, capture_output=True)
    # The bundle ships MaaPiCli without the exec bit (the GUI is the app's executable).
    PICLI.chmod(0o755)
    STAMP.write_text(want["version"] + "\n")
    print(f"MaaEnd {want['version']} installed in {VENDOR}")
    return VENDOR
