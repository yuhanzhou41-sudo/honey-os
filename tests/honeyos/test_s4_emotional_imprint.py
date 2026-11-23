"""S4: native emotional imprints for structured long-term memories.

These tests pin the S4 contract:

* EmotionalImprintStore writes a sidecar row on continuity.db
  (structured_memory_emotional_imprints) keyed by structured_memories.id.
  We never mutate structured_memories itself.

* Classification is deterministic (momentary_state._matched_axes on
  cited assistant text) — no extra LLM required to produce known /
  neutral / unknown imprints.

* Only episode / commitment / open_loop qualify for known/neutral.
  temporary_state (user transient state) lands as unknown with an
  explanatory reason.  conversation_chapters are never submitted for
  imprinting by the distillation run_id query because they use a
  different table.

* The emotion_imprint_hook_factory binds as MemoryDistiller's
  post_completed_hook once (via a mutable downstream holder for the
  U2 producer).  INSERT OR IGNORE keeps repeated distillations
  idempotent.

* Read path: EmotionalImprintStore.get(memory_id) returns None for
  every old row (schema migration is optional, not required for S4).
  Recall consumption is bounded and never auto-updates memory
  importance or injects G2 evidence.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from honeyos.companion.emotional_imprint import (
    EmotionalImprint,
    EmotionalImprintStore,
    STATUS_KNOWN,
    STATUS_NEUTRAL,
    STATUS_UNKNOWN,
    emotion_imprint_hook_factory,
    _applied_ids_for_run,
)


def _init_continuity_db(db_path: Path) -> None:
    """Create the subset of continuity tables we need for tests."""
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS structured_memories (
                id TEXT PRIMARY KEY,
                lane_key TEXT NOT NULL,
                kind TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                evidence TEXT,
                source_session_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT,
                source_message_ids TEXT,
                source_refs TEXT,
                distillation_run_id TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_sm_run_id
                ON structured_memories(distillation_run_id);
            """
        )
        conn.commit()
    finally:
        conn.close()


def _insert_memory(db_path: Path, *, mid: str, kind: str, content: str,
                   run_id: str, source_msg_ids: list[int] | None = None,
                   lane: str = "sess-1") -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO structured_memories
                (id, lane_key, kind, content, status, created_at, updated_at,
                 source_message_ids, distillation_run_id)
            VALUES (?, ?, ?, ?, 'active', datetime('now'), datetime('now'), ?, ?)
            """,
            (mid, lane, kind, content,
             json.dumps(source_msg_ids or []), run_id),
        )
        conn.commit()
    finally:
        conn.close()


def _job_messages_for(run_id: str, cited_row_ids: list[int],
                      assistant_texts: list[str],
                      user_texts: list[str] | None = None) -> list[dict]:
    """Build the subset of a DistillationJob.messages list we need."""
    msgs: list[dict] = []
    row_id = 100
    for i, text in enumerate(user_texts or []):
        msgs.append({"_row_id": row_id + i, "role": "user", "content": text,
                      "created_at": "2026-11-20T12:00:00Z"})
    row_id += len(user_texts or [])
    offset = len(user_texts or [])
    for i, text in enumerate(assistant_texts):
        msgs.append({"_row_id": row_id + i, "role": "assistant", "content": text,
                      "created_at": "2026-11-20T12:00:00Z"})
    return msgs


def _job_message(row_id: int, role: str, text: str) -> dict:
    return {
        "_row_id": row_id, "role": role, "content": text,
        "created_at": "2026-11-20T12:00:00Z",
    }


# ── 1. Classification (known / neutral / unknown) ─────────────────────────


def test_known_from_assistant_self_report(tmp_path):
    """Item A1: assistant says she liked something → known."""
    _init_continuity_db(tmp_path / "continuity.db")
    _insert_memory(tmp_path / "continuity.db", mid="m1", kind="episode",
                   content="We discussed the new design.", run_id="run-1",
                   source_msg_ids=[201])

    store = EmotionalImprintStore(tmp_path)
    msgs = [
        _job_message(100, "user", "What do you think of the design?"),
        _job_message(201, "assistant",
                     "I am curious about how it'll land.  I feel "
                     "enthusiastic about the direction."),
    ]
    created = store.upsert_for_distillation(
        distillation_run_id="run-1",
        job_messages=msgs,
        applied_memory_ids=("m1",),
        lane_key="sess-1",
    )
    assert created == 1
    imprint = store.get("m1")
    assert imprint is not None
    assert imprint.status == STATUS_KNOWN
    assert "curiosity" in imprint.basis_axes or "positive_valence" in imprint.basis_axes


def test_neutral_from_factual_assistant_reply(tmp_path):
    """Item A2: assistant reply is purely factual (no Honey-self emotion
    markers) → neutral, not unknown."""
    _init_continuity_db(tmp_path / "continuity.db")
    _insert_memory(tmp_path / "continuity.db", mid="m1", kind="episode",
                   content="We discussed the API spec.", run_id="run-1",
                   source_msg_ids=[201])
    store = EmotionalImprintStore(tmp_path)
    msgs = [
        _job_message(201, "assistant", "The endpoint accepts POST /api/v2/status "
                                       "with a JSON body containing target_id "
                                       "and optional reason.  Responses are 200 "
                                       "with an updated timestamp."),
    ]
    created = store.upsert_for_distillation(
        distillation_run_id="run-1", job_messages=msgs,
        applied_memory_ids=("m1",), lane_key="sess-1",
    )
    assert created == 1
    imprint = store.get("m1")
    assert imprint is not None
    assert imprint.status == STATUS_NEUTRAL
    assert imprint.dominant_axis is None


def test_unknown_when_no_assistant_message_cited(tmp_path):
    """Item A3: structured memory cites only user messages or has broken
    source_message_ids → unknown, with a clear summary."""
    _init_continuity_db(tmp_path / "continuity.db")
    _insert_memory(tmp_path / "continuity.db", mid="m1", kind="episode",
                   content="We talked.", run_id="run-1",
                   source_msg_ids=[999])  # not in job_messages
    store = EmotionalImprintStore(tmp_path)
    msgs = [_job_message(201, "user", "Let me tell you something")]
    created = store.upsert_for_distillation(
        distillation_run_id="run-1", job_messages=msgs,
        applied_memory_ids=("m1",), lane_key="sess-1",
    )
    assert created == 1
    imprint = store.get("m1")
    assert imprint is not None
    assert imprint.status == STATUS_UNKNOWN
    assert "No assistant reply" in imprint.evidence_summary


def test_user_bad_news_does_not_make_imprint_known(tmp_path):
    """Item A4: user's distress does not imply Honey's state — only
    assistant text matters for known status."""
    _init_continuity_db(tmp_path / "continuity.db")
    _insert_memory(tmp_path / "continuity.db", mid="m1", kind="episode",
                   content="User was upset.", run_id="run-1",
                   source_msg_ids=[201, 202])
    store = EmotionalImprintStore(tmp_path)
    msgs = [
        _job_message(201, "user", "I got laid off and I'm really down."),
        _job_message(202, "assistant", "I'm sorry to hear that.  Please tell me more "
                                       "about what happened and how you're feeling."),
    ]
    created = store.upsert_for_distillation(
        distillation_run_id="run-1", job_messages=msgs,
        applied_memory_ids=("m1",), lane_key="sess-1",
    )
    assert created == 1
    imprint = store.get("m1")
    # Assistant text is empathy but not self-expressed Honey emotion.
    assert imprint.status in (STATUS_NEUTRAL, STATUS_UNKNOWN)


# ── 2. Memory-category isolation ─────────────────────────────────────────


@pytest.mark.parametrize("kind", ["episode", "commitment", "open_loop"])
def test_eligible_kinds_get_known_or_neutral(tmp_path, kind):
    """Item B1: episode / commitment / open_loop all qualify."""
    _init_continuity_db(tmp_path / "continuity.db")
    _insert_memory(tmp_path / "continuity.db", mid=f"m-{kind}", kind=kind,
                   content="content", run_id="run-1", source_msg_ids=[201])
    store = EmotionalImprintStore(tmp_path)
    msgs = [_job_message(201, "assistant", "I think this is important — I feel "
                                           "warmly about getting it right.")]
    store.upsert_for_distillation(
        distillation_run_id="run-1", job_messages=msgs,
        applied_memory_ids=(f"m-{kind}",), lane_key="sess-1",
    )
    imprint = store.get(f"m-{kind}")
    assert imprint is not None
    assert imprint.status != STATUS_UNKNOWN
    assert imprint.status in (STATUS_KNOWN, STATUS_NEUTRAL)


def test_temporary_state_landed_as_unknown(tmp_path):
    """Item B2: temporary_state is user's own transient state — not Honey
    experiencing the event.  We record unknown with an explanatory note."""
    _init_continuity_db(tmp_path / "continuity.db")
    _insert_memory(tmp_path / "continuity.db", mid="m-ts", kind="temporary_state",
                   content="User is anxious this morning.", run_id="run-1",
                   source_msg_ids=[201])
    store = EmotionalImprintStore(tmp_path)
    msgs = [_job_message(201, "assistant", "Okay, noted.")]
    store.upsert_for_distillation(
        distillation_run_id="run-1", job_messages=msgs,
        applied_memory_ids=("m-ts",), lane_key="sess-1",
    )
    imprint = store.get("m-ts")
    assert imprint is not None
    assert imprint.status == STATUS_UNKNOWN
    assert "temporary_state" in imprint.evidence_summary


# ── 3. Idempotency ────────────────────────────────────────────────────────


def test_same_memory_id_never_receives_second_imprint(tmp_path):
    """Item C1: re-running distill_if_due on the same batch (upserting
    duplicate content) must not create a second imprint row."""
    _init_continuity_db(tmp_path / "continuity.db")
    _insert_memory(tmp_path / "continuity.db", mid="m1", kind="episode",
                   content="c", run_id="run-1", source_msg_ids=[201])
    store = EmotionalImprintStore(tmp_path)
    msgs = [_job_message(201, "assistant", "I'm curious about this.")]

    first = store.upsert_for_distillation(
        distillation_run_id="run-1", job_messages=msgs,
        applied_memory_ids=("m1",), lane_key="sess-1",
    )
    second = store.upsert_for_distillation(
        distillation_run_id="run-1", job_messages=msgs,
        applied_memory_ids=("m1",), lane_key="sess-1",
    )
    assert first == 1
    assert second == 0  # row already exists → INSERT OR IGNORE
    conn = sqlite3.connect(tmp_path / "continuity.db")
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM structured_memory_emotional_imprints "
            "WHERE memory_id = 'm1'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 1


# ── 4. Hook factory contract ─────────────────────────────────────────────


def test_hook_factory_binds_emotion_then_downstream(tmp_path):
    """Item D1: the hook runs emotion path first, then downstream if set.
    Both paths are fail-open; emotion writes sidecar rows; downstream
    receives the same args."""
    _init_continuity_db(tmp_path / "continuity.db")
    _insert_memory(tmp_path / "continuity.db", mid="m1", kind="episode",
                   content="c", run_id="run-1", source_msg_ids=[201])
    downstream_calls = []

    downstream_holder: list = [
        lambda **kw: downstream_calls.append(("called", kw["job"].run_id))
    ]
    hook = emotion_imprint_hook_factory(
        home=tmp_path, downstream_holder=downstream_holder,
    )

    class _FakeJob:
        run_id = "run-1"
        lane_key = "sess-1"
        messages = [_job_message(201, "assistant", "I feel positive about this.")]

    class _FakeResult:
        status = "completed"
        applied = 1

    hook(job=_FakeJob(), result=_FakeResult(), main_runtime=None)

    store = EmotionalImprintStore(tmp_path)
    assert store.get("m1") is not None
    assert downstream_calls == [("called", "run-1")]


def test_hook_factory_downstream_is_optional(tmp_path):
    """Item D2: no downstream holder → emotion still runs fine, no errors."""
    _init_continuity_db(tmp_path / "continuity.db")
    _insert_memory(tmp_path / "continuity.db", mid="m1", kind="episode",
                   content="c", run_id="run-1", source_msg_ids=[201])
    hook = emotion_imprint_hook_factory(home=tmp_path)  # no downstream_holder

    class _FakeJob:
        run_id = "run-1"
        lane_key = "sess-1"
        messages = [_job_message(201, "assistant", "I'm curious.")]

    class _FakeResult:
        status = "completed"
        applied = 1

    hook(job=_FakeJob(), result=_FakeResult(), main_runtime=None)

    store = EmotionalImprintStore(tmp_path)
    assert store.get("m1") is not None


def test_hook_factory_downstream_error_is_swallowed(tmp_path):
    """Item D3: downstream raising an exception must not break emotion
    imprinting.  Emotion runs first and should succeed regardless."""
    _init_continuity_db(tmp_path / "continuity.db")
    _insert_memory(tmp_path / "continuity.db", mid="m1", kind="episode",
                   content="c", run_id="run-1", source_msg_ids=[201])

    def _boom(**_kw):
        raise RuntimeError("downstream exploded")

    hook = emotion_imprint_hook_factory(
        home=tmp_path, downstream_holder=[_boom],
    )

    class _FakeJob:
        run_id = "run-1"
        lane_key = "sess-1"
        messages = [_job_message(201, "assistant", "I feel positive.")]

    class _FakeResult:
        status = "completed"
        applied = 1

    # Must NOT raise.
    hook(job=_FakeJob(), result=_FakeResult(), main_runtime=None)

    store = EmotionalImprintStore(tmp_path)
    assert store.get("m1") is not None  # emotion path still wrote


def test_hook_factory_skips_non_completed(tmp_path):
    """Item D4: status != completed or applied == 0 → nothing written."""
    hook = emotion_imprint_hook_factory(home=tmp_path)

    class _Job:
        run_id = "run-1"
        lane_key = ""
        messages = []

    class _Result:
        status = "failed"
        applied = 1

    hook(job=_Job(), result=_Result())

    class _Result2:
        status = "completed"
        applied = 0

    hook(job=_Job(), result=_Result2())  # no applied memories → skip

    store = EmotionalImprintStore(tmp_path)
    # No continuity.db created at all (store is lazy in _connect).
    assert not (tmp_path / "continuity.db").exists()


# ── 5. Hook factory downstream_holder mutation ───────────────────────────


def test_downstream_holder_can_be_mutated_after_bind(tmp_path):
    """Item D5: downstream is looked up from the mutable list on every
    hook call — so U2 can be hot-enabled by replacing holder[0]."""
    _init_continuity_db(tmp_path / "continuity.db")
    _insert_memory(tmp_path / "continuity.db", mid="m1", kind="episode",
                   content="c", run_id="run-1", source_msg_ids=[201])
    calls: list[str] = []
    holder: list = [None]
    hook = emotion_imprint_hook_factory(home=tmp_path, downstream_holder=holder)

    class _Job:
        run_id = "run-1"
        lane_key = ""
        messages = [_job_message(201, "assistant", "I'm warm.")]

    class _Result:
        status = "completed"
        applied = 1

    # First call: no downstream → emotion writes, downstream does not run.
    hook(job=_Job(), result=_Result())
    assert not calls

    # Second call: holder[0] now has a callable → downstream runs.
    holder[0] = lambda **kw: calls.append("u2-ran")
    hook(job=_Job(), result=_Result())
    assert calls == ["u2-ran"]


# ── 6. Read / recall path ────────────────────────────────────────────────


def test_get_returns_none_for_unknown_memory(tmp_path):
    """Item E1: EmotionalImprintStore.get on a memory_id with no sidecar
    row (e.g. imported DeepSeek / old row) → None."""
    _init_continuity_db(tmp_path / "continuity.db")
    store = EmotionalImprintStore(tmp_path)
    assert store.get("no-such-memory") is None


def test_get_returns_parsed_dataclass_for_known_row(tmp_path):
    """Item E2: EmotionalImprintStore.get parses JSON fields into tuples."""
    _init_continuity_db(tmp_path / "continuity.db")
    _insert_memory(tmp_path / "continuity.db", mid="m1", kind="episode",
                   content="c", run_id="run-1", source_msg_ids=[201])
    store = EmotionalImprintStore(tmp_path)
    msgs = [_job_message(201, "assistant", "I'm curious and warm.")]
    store.upsert_for_distillation(
        distillation_run_id="run-1", job_messages=msgs,
        applied_memory_ids=("m1",), lane_key="sess-1",
    )
    imprint = store.get("m1")
    assert isinstance(imprint, EmotionalImprint)
    assert isinstance(imprint.basis_axes, tuple)
    assert "curiosity" in imprint.basis_axes or "warmth" in imprint.basis_axes
    assert isinstance(imprint.basis_turn_ids, tuple)
    assert 201 in imprint.basis_turn_ids


# ── 7. continuity.db does not create sidecar for invalid home ─────────────


def test_upsert_handles_missing_continuity_db_gracefully(tmp_path):
    """Item F1: if continuity.db has no structured_memories table yet, upsert
    returns 0 instead of raising.  sqlite3.connect will create the empty
    file (by design of Python's sqlite3), but the write never touches the
    sidecar and no imprint row is written."""
    store = EmotionalImprintStore(tmp_path)
    # No structured_memories table in the empty continuity.db that
    # sqlite3.connect creates on first call — so the upsert path hits
    # OperationalError inside the try block, logs, and returns 0.
    created = store.upsert_for_distillation(
        distillation_run_id="run-1",
        job_messages=[],
        applied_memory_ids=("no-such-id",),
        lane_key="",
    )
    assert created == 0


def test_applied_ids_for_run_returns_empty_tuple_when_no_match(tmp_path):
    """Item F2: _applied_ids_for_run returns () for an unknown run_id."""
    _init_continuity_db(tmp_path / "continuity.db")
    ids = _applied_ids_for_run(tmp_path, "no-run")
    assert ids == ()


# ── 8. no_extra_llm_call hard requirement ────────────────────────────────


def test_emotion_imprint_module_has_no_llm_callers():
    """Item G1 (hard): the emotion_imprint module must NOT import or
    reference any LLM client.  All classification is regex-driven."""
    import honeyos.companion.emotional_imprint as mod
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("call_llm", "LLMProvider", "AuxiliaryClient",
                      "distill_with_llm", "from honeyos.agent",
                      "client.chat.completions", "requests.post"):
        assert forbidden not in src, f"{forbidden} leaked into emotional_imprint"
