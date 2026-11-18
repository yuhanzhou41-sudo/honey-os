"""Command line entry: ``python -m honeyos.study.textbook ...``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .android_bridge import AndroidBridge, MuMuManager, wait_for_device
from .service import TextbookService, default_textbook_root


def _service(args) -> TextbookService:
    return TextbookService(root=args.root)


def _print(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _section(service: TextbookService, book_id: str, value: str):
    outline = service.get_outline(book_id)
    try:
        return outline.section(value)
    except KeyError:
        pass
    for section in outline.sections:
        if value in section.title:
            return section
    raise SystemExit(f"目录中没有匹配的章节：{value}")


def cmd_devices(args) -> int:
    bridge = AndroidBridge()
    _print({"adb": bridge.adb_path, "serial": bridge.serial,
            "devices": [row.__dict__ for row in bridge.devices()]})
    return 0


def cmd_boot(args) -> int:
    manager = MuMuManager()
    launched = manager.launch(args.instance)
    bridge = AndroidBridge(serial=args.serial or None)
    online = wait_for_device(bridge, timeout=args.timeout)
    _print({"launched": launched, "online": online, "serial": bridge.serial})
    return 0 if online else 1


def cmd_index_dump(args) -> int:
    service = _service(args)
    dump = Path(args.dump_file).read_text(encoding="utf-8")
    outline = service.sync_outline_from_dump(args.book, dump, title=args.title, package=args.package)
    _print({"book_id": outline.book_id, "title": outline.title,
            "sections": [item.to_dict() for item in outline.sections]})
    return 0


def cmd_index_text(args) -> int:
    service = _service(args)
    text = Path(args.text_file).read_text(encoding="utf-8")
    outline = service.sync_outline_from_text(args.book, text, title=args.title)
    _print({"book_id": outline.book_id, "sections": len(outline.sections)})
    return 0


def cmd_sync_toc(args) -> int:
    service = _service(args)
    outline = service.sync_outline_from_device(args.book, title=args.title)
    _print({
        "book_id": outline.book_id,
        "title": outline.title,
        "sections": len(outline.sections),
        "chapters": [item.get("title") for item in outline.source.get("chapters", [])],
    })
    return 0


def cmd_locate(args) -> int:
    service = _service(args)
    _print({"query": args.query, "hits": service.locate(args.query, book_id=args.book, limit=args.limit)})
    return 0


def cmd_collect(args) -> int:
    service = _service(args)
    section = _section(service, args.book, args.section)
    payload = service.collect_section(args.book, section.section_id, force=args.force,
                                      progress=lambda state: print(json.dumps(state), file=sys.stderr))
    text = payload.pop("text", "")
    payload["preview"] = text[:400]
    _print(payload)
    return 0


def cmd_reindex(args) -> int:
    from honeyos.study.library import StudyLibraryIndex
    from honeyos.study.repository import StudyRepository

    count = StudyLibraryIndex(StudyRepository().db_path).reindex_all()
    _print({"reindexed": count})
    return 0


def cmd_stats(args) -> int:
    _print(_service(args).stats())
    return 0


def cmd_cleanup(args) -> int:
    service = _service(args)
    if args.purge_temp:
        _print({"temp": service.purge_temp()})
        return 0
    _print(service.cleanup(max_bytes=args.max_bytes, ttl_days=args.ttl_days))
    return 0


def cmd_release(args) -> int:
    service = _service(args)
    outline = service.get_outline(args.book)
    ids = []
    for value in args.section:
        ids.append(_section(service, args.book, value).section_id)
    _print(service.release_after_review(outline.book_id, ids))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="honeyos-textbook", description="HoneyOS 按需教材采集")
    parser.add_argument("--root", default=None, help=f"教材缓存根目录（默认 {default_textbook_root()}）")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("devices", help="列出 adb 设备").set_defaults(func=cmd_devices)

    boot = sub.add_parser("boot", help="启动 MuMu 实例并等待 adb 在线")
    boot.add_argument("--instance", type=int, default=0)
    boot.add_argument("--serial", default=None)
    boot.add_argument("--timeout", type=float, default=90)
    boot.set_defaults(func=cmd_boot)

    index_dump = sub.add_parser("index-dump", help="用 UI dump 建立章节索引")
    index_dump.add_argument("--book", required=True)
    index_dump.add_argument("--title", default="")
    index_dump.add_argument("--dump-file", required=True)
    index_dump.add_argument("--package", default="com.pmph.irenwei")
    index_dump.set_defaults(func=cmd_index_dump)

    index_text = sub.add_parser("index-text", help="用目录文本建立章节索引")
    index_text.add_argument("--book", required=True)
    index_text.add_argument("--title", default="")
    index_text.add_argument("--text-file", required=True)
    index_text.set_defaults(func=cmd_index_text)

    sync_toc = sub.add_parser("sync-toc", help="打开 APP 目录并抓取章节树")
    sync_toc.add_argument("--book", required=True)
    sync_toc.add_argument("--title", default="")
    sync_toc.set_defaults(func=cmd_sync_toc)

    locate = sub.add_parser("locate", help="按学习需求定位章节")
    locate.add_argument("--book", default=None)
    locate.add_argument("--limit", type=int, default=3)
    locate.add_argument("query")
    locate.set_defaults(func=cmd_locate)

    collect = sub.add_parser("collect", help="采集单节正文")
    collect.add_argument("--book", required=True)
    collect.add_argument("--section", required=True, help="章节编号或标题片段")
    collect.add_argument("--force", action="store_true")
    collect.set_defaults(func=cmd_collect)

    sub.add_parser("stats", help="查看缓存占用").set_defaults(func=cmd_stats)

    sub.add_parser("reindex", help="重建 Study 资料的全文索引（中文分段）").set_defaults(func=cmd_reindex)

    cleanup = sub.add_parser("cleanup", help="清理临时截图与超限缓存")
    cleanup.add_argument("--purge-temp", action="store_true")
    cleanup.add_argument("--max-bytes", type=int, default=None)
    cleanup.add_argument("--ttl-days", type=float, default=None)
    cleanup.set_defaults(func=cmd_cleanup)

    release = sub.add_parser("release", help="复习完成后释放章节缓存与派生资料")
    release.add_argument("--book", required=True)
    release.add_argument("--section", action="append", required=True)
    release.set_defaults(func=cmd_release)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
