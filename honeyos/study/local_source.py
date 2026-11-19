"""Resolve explicitly selected Windows files without creating a managed copy."""

from __future__ import annotations

import hashlib
from pathlib import Path, PureWindowsPath
import re
import stat

TEXT_FORMATS = frozenset({".txt", ".md", ".markdown", ".json", ".csv", ".tsv", ".xml"})
DOCUMENT_FORMATS = frozenset({".pdf", ".docx", ".pptx", ".xlsx"})


def resolve_local_source(value: str, mount_root: Path) -> Path:
    value = str(value or "").strip().strip('"')
    if not value or len(value) > 4096 or "\x00" in value:
        raise ValueError("请输入完整的 Windows 文件路径")
    windows = PureWindowsPath(value)
    root = mount_root.resolve()
    if re.fullmatch(r"[a-zA-Z]:", windows.drive) and windows.is_absolute():
        drive = windows.drive[0].lower()
        relative = windows.parts[1:]
        if any(":" in part for part in relative):
            raise ValueError("不支持文件的备用数据流")
    else:
        try:
            drive, *relative = Path(value).relative_to(root).parts
        except ValueError as exc:
            raise ValueError("请输入 Windows 盘符路径，例如 D:\\教材\\讲义.pdf") from exc
        if not re.fullmatch(r"[a-z]", drive):
            raise ValueError("请输入完整的 Windows 文件路径")
    if not relative or ".." in relative:
        raise ValueError("请选择盘符中的一个文件")
    drive_root = root / drive
    try:
        if drive_root.is_symlink():
            raise ValueError("驱动器路径不在允许范围")
        path = drive_root.joinpath(*relative).resolve(strict=True)
        path.relative_to(drive_root)
        if not stat.S_ISREG(path.stat().st_mode):
            raise ValueError("请选择普通文件")
    except OSError as exc:
        raise ValueError("无法读取原文件，请检查路径和磁盘连接") from exc
    except RuntimeError as exc:
        raise ValueError("无法解析原文件路径") from exc
    return path


def source_signature(path: Path) -> tuple[int, int, int, int]:
    info = path.stat()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def local_source_metadata(path: Path, max_bytes: int) -> dict:
    signature = source_signature(path)
    if signature[2] > max_bytes:
        raise ValueError(f"文件超过 {max_bytes // (1024 * 1024)} MB 的资料导入上限")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if signature != source_signature(path):
        raise ValueError("文件读取期间发生变化，请重试")
    return {"path": str(path), "sha256": digest, "size_bytes": signature[2], "mtime_ns": signature[3]}


def local_source_status(source: dict) -> str:
    try:
        _, _, size, mtime = source_signature(Path(source["path"]))
    except (OSError, KeyError):
        return "offline"
    return "online" if (size, mtime) == (source["size_bytes"], source["mtime_ns"]) else "changed"


def extract_local_source(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in TEXT_FORMATS:
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("文本文档需要使用 UTF-8 编码") from exc
    if suffix not in DOCUMENT_FORMATS:
        raise ValueError("不支持此文档格式")
    from honeyos.tools.read_extract import ExtractionError, extract_document_text

    try:
        return extract_document_text(str(path))
    except ExtractionError as exc:
        raise ValueError("无法提取文档正文，扫描件需要 OCR") from exc
