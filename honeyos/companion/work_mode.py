"""Profile-local work lifecycle and per-turn tool scope."""

from contextlib import closing, contextmanager
from contextvars import ContextVar
from pathlib import Path
import sqlite3
from uuid import uuid4

from honeyos.core.constants import get_honeyos_home

work_turn = ContextVar("honeyos_work_turn", default=None)
WORK_GUIDANCE = (
    "You are in work mode. Inspect the candidate workspace and use the work tools when "
    "they can advance the task. Establish the objective and acceptance checks, make the "
    "smallest candidate change, verify it, and summarize the result. Use clarify when "
    "a consequential requirement is missing. An approval applies to one exact action. "
    "Tie any skill or feature idea to a real task or observed limitation."
)


def _root() -> Path:
    return get_honeyos_home() / "work"


@contextmanager
def _connect():
    root = _root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with closing(sqlite3.connect(root / "control.sqlite")) as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS active_work (
            slot INTEGER PRIMARY KEY CHECK(slot=1), id TEXT NOT NULL,
            session_id TEXT NOT NULL, summary TEXT NOT NULL DEFAULT ''
        )""")
        yield db


def active_work() -> tuple[str, str] | None:
    if not (_root() / "control.sqlite").is_file():
        return None
    with _connect() as db:
        return db.execute("SELECT id,session_id FROM active_work WHERE slot=1").fetchone()


def start_work(session_id: str) -> tuple[str, str]:
    with _connect() as db:
        db.execute("INSERT OR IGNORE INTO active_work (slot,id,session_id) VALUES (1,?,?)",
                   (uuid4().hex, session_id))
        return db.execute("SELECT id,session_id FROM active_work WHERE slot=1").fetchone()


def finish_work() -> tuple[str, str, str] | None:
    with _connect() as db:
        return db.execute("DELETE FROM active_work WHERE slot=1 RETURNING id,session_id,summary").fetchone()


def save_summary(work_id: str, summary: str) -> None:
    with _connect() as db:
        db.execute("UPDATE active_work SET summary=? WHERE id=?", (summary, work_id))


def workspace(work_id: str) -> Path:
    from honeyos.companion.projects import project_root

    return project_root(get_honeyos_home()) / "HoneyOS Work" / work_id


def schedule_work_review(work_id: str, session_id: str, summary: str) -> None:
    from honeyos.companion.pre_reply_appraisal import appraise_before_reply, schedule_reply_appraisal

    home = get_honeyos_home()
    schedule_reply_appraisal(
        lambda: appraise_before_reply(
            home, session_id, "work-" + work_id,
            "Honey 已结束这次工作。以下是工作结果，不是用户情绪：" + summary[:720],
            recent=(), recalled="", cancelled=lambda: bool(active_work()),
        ),
        {"final_response": "work completed"},
    )
