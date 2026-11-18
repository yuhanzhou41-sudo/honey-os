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
# The gateway runs inside WSL; executing the Windows binary through interop keeps
# adb talking to the emulator on the Windows side of the NAT.
WSL_MUMU_ADB = Path("/mnt/d/Program Files/Netease/MuMu/nx_main/adb.exe")
WSL_MUMU_MANAGER = Path("/mnt/d/Program Files/Netease/MuMu/nx_main/MuMuManager.exe")
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
    for candidate in (MUMU_ADB, WSL_MUMU_ADB):
        if candidate.is_file():
            return str(candidate)
    return shutil.which("adb") or "adb"


def default_mumu_manager() -> Path:
    for candidate in (MUMU_MANAGER, WSL_MUMU_MANAGER):
        if candidate.is_file():
            return candidate
    return MUMU_MANAGER


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

    def _run(self, args: Sequence[str], *, timeout: float | None = None, retry: bool = True) -> str:
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
            dropped = "not found" in error or "offline" in error or "no devices" in error
            if retry and dropped and ":" in self.serial:
                self._run(["connect", self.serial], timeout=20, retry=False)
                return self._run(args, timeout=timeout, retry=False)
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

    def connect(self) -> bool:
        """Attach a TCP serial (emulator restarts drop the connection)."""
        if ":" not in self.serial:
            return False
        try:
            self._run(["connect", self.serial], timeout=20)
        except AdbError:
            return False
        return self.online()

    def ensure_online(self) -> None:
        if self.online():
            return
        self.connect()
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

    def find_text_center(self, text: str, *, dump: str | None = None) -> tuple[int, int] | None:
        import re
        import xml.etree.ElementTree as ET

        source = dump if dump is not None else self.dump_ui()
        try:
            root = ET.fromstring(source)
        except ET.ParseError:
            return None
        target = re.sub(r"\s+", "", text)
        for node in root.iter():
            label = re.sub(r"\s+", "", node.get("text") or node.get("content-desc") or "")
            if target and target in label:
                match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", (node.get("bounds") or "").strip())
                if match:
                    x1, y1, x2, y2 = (int(part) for part in match.groups())
                    return (x1 + x2) // 2, (y1 + y2) // 2
        return None

    def tap_text(self, text: str, *, dump: str | None = None) -> bool:
        spot = self.find_text_center(text, dump=dump)
        if spot is None:
            return False
        self.tap(*spot)
        return True

    def open_toc(self) -> str:
        """Open the reading app's table of contents drawer and return its dump.

        The drawer is reached from the floating green dot on the left edge;
        tapping the bottom toolbar's 目录 entry also opens it when visible.
        """
        dump = self.dump_ui()
        if "书签" in dump and "笔记" in dump:
            return dump
        width, height = self.screen_size()
        self.tap(int(width * 0.026), int(height * 0.5))
        time.sleep(0.9)
        dump = self.dump_ui()
        if "书签" in dump and "笔记" in dump:
            return dump
        if self.tap_text("目录", dump=dump):
            time.sleep(0.9)
            return self.dump_ui()
        return dump


class MuMuManager:
    """Start the emulator instance through MuMuManager when it is not running."""

    def __init__(self, manager_path: Path | str | None = None, runner=subprocess.run):
        self.manager_path = Path(manager_path) if manager_path else default_mumu_manager()
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
        bridge.connect()
        time.sleep(interval)
    return False


def iter_ui_texts(dump: str) -> Iterable[str]:
    for piece in dump.split('text="')[1:]:
        yield piece.split('"', 1)[0]
