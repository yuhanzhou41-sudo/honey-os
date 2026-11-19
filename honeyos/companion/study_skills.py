"""Local registry for the declarative Study review-note skill."""

from contextlib import closing, contextmanager
from hashlib import sha256
import json
import sqlite3

from honeyos.core.constants import get_honeyos_home


@contextmanager
def _connect():
    root = get_honeyos_home() / "work"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with closing(sqlite3.connect(root / "study_skills.sqlite")) as db, db:
        db.row_factory = sqlite3.Row
        db.executescript("""
            CREATE TABLE IF NOT EXISTS candidate (
                version INTEGER PRIMARY KEY, digest TEXT NOT NULL UNIQUE,
                work_id TEXT NOT NULL, manifest TEXT NOT NULL,
                approved INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS selected (
                slot INTEGER PRIMARY KEY CHECK(slot=1),
                version INTEGER REFERENCES candidate(version)
            );
            INSERT OR IGNORE INTO selected (slot, version) VALUES (1, NULL);
        """)
        yield db


def validate_manifest(value: dict) -> str:
    fields = {"name", "purpose", "heading"}
    if not isinstance(value, dict) or value.keys() != fields:
        raise ValueError("候选必须包含 name、purpose 和 heading。")
    limits = {"name": 48, "purpose": 240, "heading": 64}
    for key, limit in limits.items():
        item = value[key]
        if not isinstance(item, str) or not 1 <= len(item.strip()) <= limit or not item.isprintable():
            raise ValueError(f"候选字段 {key} 必须是长度不超过 {limit} 的单行文字。")
    return json.dumps({key: value[key].strip() for key in sorted(fields)}, ensure_ascii=False)


def _format_note(manifest: dict, notes: str) -> str:
    if not isinstance(notes, str) or not notes.strip() or len(notes) > 12000:
        raise ValueError("请输入 1 至 12000 字的复习内容。")
    return "\n".join([manifest["heading"], "", *(f"• {line.strip()}" for line in notes.splitlines() if line.strip())])


def _test(manifest: dict) -> list[str]:
    sample = "脉搏不对称\n\n记录患侧"
    if _format_note(manifest, sample) != manifest["heading"] + "\n\n• 脉搏不对称\n• 记录患侧":
        raise ValueError("复习笔记格式验证失败。")
    try:
        _format_note(manifest, "  ")
    except ValueError:
        return ["合成样本按行整理", "拒绝空白输入"]
    raise ValueError("空白输入验证失败。")


def submit(manifest: str, work_id: str) -> int:
    normalized = validate_manifest(json.loads(manifest))
    _test(json.loads(normalized))
    digest = sha256(normalized.encode()).hexdigest()
    with _connect() as db:
        db.execute("INSERT OR IGNORE INTO candidate (digest, work_id, manifest) VALUES (?, ?, ?)",
                   (digest, work_id, normalized))
        return db.execute("SELECT version FROM candidate WHERE digest=?", (digest,)).fetchone()[0]


def status() -> dict:
    with _connect() as db:
        active = db.execute("SELECT version FROM selected WHERE slot=1").fetchone()[0]
        rows = db.execute("SELECT * FROM candidate ORDER BY version DESC").fetchall()
    return {
        "active_version": active,
        "candidates": [{
            "version": row["version"], "digest": row["digest"], "work_id": row["work_id"],
            "approved": bool(row["approved"]), "manifest": json.loads(row["manifest"]),
            "checks": _test(json.loads(row["manifest"])),
        } for row in rows],
    }


def change(action: str, version: int, digest: str) -> None:
    if action not in ("enable", "disable", "rollback") or type(version) is not int or not isinstance(digest, str):
        raise ValueError("请选择有效的操作与版本。")
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM candidate WHERE version=? AND digest=?", (version, digest)).fetchone()
        if row is None or sha256(row["manifest"].encode()).hexdigest() != digest:
            raise ValueError("候选版本已变化，请刷新审核清单。")
        current = db.execute("SELECT version FROM selected WHERE slot=1").fetchone()[0]
        if action == "disable":
            if current != version:
                raise ValueError("此版本已停用。")
            db.execute("UPDATE selected SET version=NULL WHERE slot=1")
            return
        if action == "rollback" and (not row["approved"] or (current is not None and version >= current)):
            raise ValueError("请选择已审核的较早版本。")
        _test(json.loads(row["manifest"]))
        db.execute("UPDATE candidate SET approved=1 WHERE version=?", (version,))
        db.execute("UPDATE selected SET version=? WHERE slot=1", (version,))


def run(notes: str) -> str:
    with _connect() as db:
        row = db.execute("""SELECT manifest, digest FROM candidate JOIN selected USING (version)
                            WHERE slot=1 AND approved=1""").fetchone()
    if row is None or sha256(row["manifest"].encode()).hexdigest() != row["digest"]:
        raise ValueError("请先启用通过审核的复习笔记 Skill。")
    return _format_note(json.loads(row["manifest"]), notes)
