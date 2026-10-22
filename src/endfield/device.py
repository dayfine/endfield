import contextlib
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from endfield.config import Config


class DeviceError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeviceInfo:
    serial: str
    model: str
    android: str
    physical_size: str
    override_size: str | None
    game_version: str | None


class Device:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def _adb(self, *args: str, binary: bool = False) -> bytes | str:
        cmd = [self.cfg.adb, "-s", self.cfg.serial, *args]
        proc = subprocess.run(cmd, capture_output=True, timeout=60)
        if proc.returncode != 0:
            err = proc.stderr.decode(errors="replace").strip()
            raise DeviceError(f"{' '.join(args)}: {err}")
        return proc.stdout if binary else proc.stdout.decode(errors="replace")

    def shell(self, command: str) -> str:
        return self._adb("shell", command)

    def is_connected(self) -> bool:
        out = subprocess.run(
            [self.cfg.adb, "devices"], capture_output=True, text=True, timeout=30
        ).stdout
        return any(
            line.split("\t") == [self.cfg.serial, "device"] for line in out.splitlines()
        )

    def sizes(self) -> tuple[str, str | None]:
        """Returns (physical, override) as WxH strings, portrait orientation."""
        physical, override = "", None
        for line in self.shell("wm size").splitlines():
            key, _, value = line.partition(":")
            if key.strip() == "Physical size":
                physical = value.strip()
            elif key.strip() == "Override size":
                override = value.strip()
        return physical, override

    def game_version(self) -> str | None:
        out = self.shell(f"dumpsys package {self.cfg.package}")
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("versionName="):
                return line.removeprefix("versionName=")
        return None

    def info(self) -> DeviceInfo:
        physical, override = self.sizes()
        return DeviceInfo(
            serial=self.cfg.serial,
            model=self.shell("getprop ro.product.model").strip(),
            android=self.shell("getprop ro.build.version.release").strip(),
            physical_size=physical,
            override_size=override,
            game_version=self.game_version(),
        )

    def screenshot(self, path: Path) -> Path:
        png = self._adb("exec-out", "screencap", "-p", binary=True)
        if not png.startswith(b"\x89PNG"):
            raise DeviceError("screencap did not return a PNG")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png)
        return path

    def set_size(self, size: str | None) -> None:
        self.shell(f"wm size {size}" if size else "wm size reset")

    @contextlib.contextmanager
    def forced_size(self) -> Iterator[None]:
        """Force the configured 16:9 size for the duration, always resetting after."""
        if not self.cfg.force_size:
            yield
            return
        self.set_size(self.cfg.force_size)
        try:
            yield
        finally:
            self.set_size(None)
