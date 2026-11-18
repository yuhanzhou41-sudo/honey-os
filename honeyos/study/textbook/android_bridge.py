"""Thin ADB bridge for the reading app running in an Android emulator.

Only UI automation primitives live here. Screenshots are written to a caller
provided temporary path so that they can be removed right after OCR.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

MUMU_ADB = Path(r"D:\Program Files\Netease\MuMu\nx_main\adb.exe")
MUMU_MANAGER = Path(r"D:\Program Files\Netease\MuMu\nx_main\MuMuManager.exe")
REMOTE_SHOT = "/sdcard/honeyos_capture.png"


class AdbError(RuntimeError):
    pass


@dataclass(frozen=True)
class AdbDevice:
    serial: str
    state: str


def default_adb_path() -> str:
    configured = os.environ.get("HONEYOS_ADB_PATH")
    if configured:
        return configured
    if MUMU_ADB.is_file():
        return str(MUMU_ADB)
    return shutil.which("adb") or "adb"


def default_serial() -> str:
    return os.environ.get("HONEYOS_ADB_SERIAL", "127.0.0.1:16384")


class AndroidBridge:
    def __init__(
        self,
        adb_path: str | None = None,
        serial: str | None = None,
        *,
        timeout: float = 60.0,
        runner=subprocess.run,
    ):
        self.adb_path = adb_path or default_adb_path()
        self.serial = serial or default_serial()
        self.timeout = float(timeout)
        self._runner = runner

    def _run(self, args: Sequence[str], *, timeout: float | None = None) -> str:
        command = [self.adb_path]
        if self.serial:
            command.extend(["-s", self.serial])
        command.extend(str(item) for item in args)
        try:
            result = self._runner(
                command,
                capture_output=True,
                timeout=timeout or self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise AdbError(f"找不到 adb：{self.adb_path}") from exc
        except subprocess.TimeoutExpired as exc:
            raise AdbError("adb 命令超时，请检查模拟器是否卡住") from exc
        output = (result.stdout or b"").decode("utf-8", "replace")
        error = (result.stderr or b"").decode("utf-8", "replace").strip()
        if result.returncode != 0:
            raise AdbError(error or f"adb 命令失败：{' '.join(command)}")
        return output

    def devices(self) -> list[AdbDevice]:
        rows: list[AdbDevice] = []
        for line in self._run(["devices"]).splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2:
                rows.append(AdbDevice(parts[0], parts[1]))
        return rows

    def online(self) -> bool:
        try:
            return any(row.state == "device" for row in self.devices())
        except AdbError:
            return False

    def ensure_online(self) -> None:
        if not self.online():
            raise AdbError(
                "模拟器 adb 不在线。请先启动 MuMu 实例并确认 adb devices 中有 device。"
            )

    def launch(self, package: str) -> None:
        self._run(["shell", "monkey", "-p", str(package), "-c", "android.intent.category.LAUNCHER", "1"])

    def dump_ui(self) -> str:
        # Some Android builds let uiautomator exit non-zero (SIGSEGV) after a
        # successful dump, so the artifact is the source of truth, not the code.
        try:
            self._run(["shell", "uiautomator", "dump", "/sdcard/honeyos_ui.xml"])
        except AdbError:
            pass
        try:
            return self._run(["shell", "cat", "/sdcard/honeyos_ui.xml"])
        except AdbError as exc:
            raise AdbError(f"无法读取界面层级：{exc}") from exc

    def tap(self, x: int, y: int) -> None:
        self._run(["shell", "input", "tap", str(int(x)), str(int(y))])

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 320) -> None:
        self._run(
            ["shell", "input", "swipe", str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(int(duration_ms))]
        )

    def screen_size(self) -> tuple[int, int]:
        output = self._run(["shell", "wm", "size"])
        for token in output.replace(":", " ").split():
            if "x" in token and token.replace("x", "").isdigit():
                width, height = token.split("x", 1)
                return int(width), int(height)
        raise AdbError("无法读取模拟器分辨率")

    def screencap(self, destination: Path | str) -> Path:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._run(["shell", "screencap", "-p", REMOTE_SHOT])
        try:
            self._run(["pull", REMOTE_SHOT, str(target)])
        finally:
            try:
                self._run(["shell", "rm", "-f", REMOTE_SHOT])
            except AdbError:
                pass
        if not target.is_file() or target.stat().st_size == 0:
            raise AdbError("截图失败：没有得到图片数据")
        return target

    def install(self, apk: Path | str) -> str:
        return self._run(["install", "-r", str(apk)], timeout=600)

    def shell(self, *args: str) -> str:
        return self._run(["shell", *args])


class MuMuManager:
    """Start the emulator instance through MuMuManager when it is not running."""

    def __init__(self, manager_path: Path | str = MUMU_MANAGER, runner=subprocess.run):
        self.manager_path = Path(manager_path)
        self._runner = runner

    def available(self) -> bool:
        return self.manager_path.is_file()

    def launch(self, index: int = 0, *, wait_seconds: float = 0.0) -> bool:
        if not self.available():
            return False
        try:
            result = self._runner(
                [str(self.manager_path), "control", "-v", str(int(index)), "launch"],
                capture_output=True,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        if wait_seconds > 0:
            time.sleep(float(wait_seconds))
        return result.returncode == 0


def wait_for_device(bridge: AndroidBridge, *, timeout: float = 90.0, interval: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if bridge.online():
            return True
        time.sleep(interval)
    return False


def iter_ui_texts(dump: str) -> Iterable[str]:
    for piece in dump.split('text="')[1:]:
        yield piece.split('"', 1)[0]
