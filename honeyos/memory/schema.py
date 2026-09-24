from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 2

DDL = r"""
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_episodes (
    episode_id TEXT PRIMARY KEY,
    episode_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    occurred_at TEXT,
    captured_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('active','superseded','dormant','user_suppressed')
    ),
    memory_origin TEXT NOT NULL DEFAULT 'native'
        CHECK(memory_origin IN ('native','external')),
    source_system TEXT NOT NULL,
    source_scope TEXT,
    source_key TEXT,
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    content_fingerprint TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_memory_episodes_status
    ON memory_episodes(status);
CREATE INDEX IF NOT EXISTS idx_memory_episodes_fingerprint
    ON memory_episodes(content_fingerprint);

CREATE TABLE IF NOT EXISTS memory_provenance (
    provenance_id TEXT PRIMARY KEY,
    memory_kind TEXT NOT NULL CHECK (
        memory_kind IN ('episode','fact','procedural')
    ),
    memory_id TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT,
    session_id TEXT,
    message_id TEXT,
    evidence_quote TEXT,
    content_hash TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memory_provenance_memory
    ON memory_provenance(memory_kind, memory_id);

CREATE TABLE IF NOT EXISTS memory_facts (
    fact_id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_text TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('current','superseded','dormant','user_suppressed')
    ),
    valid_from TEXT,
    valid_to TEXT,
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    derived_from_episode_id TEXT,
    memory_origin TEXT NOT NULL DEFAULT 'native'
        CHECK(memory_origin IN ('native','external')),
    source_system TEXT NOT NULL DEFAULT 'honeyos',
    source_scope TEXT,
    source_key TEXT,
    content_fingerprint TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (derived_from_episode_id)
        REFERENCES memory_episodes(episode_id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_memory_facts_subject
    ON memory_facts(subject);
CREATE INDEX IF NOT EXISTS idx_memory_facts_fingerprint
    ON memory_facts(content_fingerprint);

CREATE TABLE IF NOT EXISTS memory_edges (
    edge_id TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_kind TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation TEXT NOT NULL CHECK (
        relation IN (
            'supports',
            'contradicts',
            'supersedes',
            'continuation_of',
            'part_of',
            'related_to',
            'caused_by',
            'derived_from'
        )
    ),
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_salience (
    memory_kind TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    personal_relevance REAL NOT NULL DEFAULT 0,
    emotional_valence REAL NOT NULL DEFAULT 0,
    arousal REAL NOT NULL DEFAULT 0,
    user_emphasis REAL NOT NULL DEFAULT 0,
    unresolvedness REAL NOT NULL DEFAULT 0,
    sensitivity REAL NOT NULL DEFAULT 0,
    recall_affinity REAL NOT NULL DEFAULT 0,
    mention_sensitivity REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (memory_kind, memory_id)
);

CREATE TABLE IF NOT EXISTS procedural_memories (
    procedure_id TEXT PRIMARY KEY,
    key TEXT NOT NULL,
    instruction TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('active','superseded','dormant','user_suppressed')
    ),
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    valid_from TEXT,
    valid_to TEXT,
    memory_origin TEXT NOT NULL DEFAULT 'native'
        CHECK(memory_origin IN ('native','external')),
    source_system TEXT NOT NULL DEFAULT 'honeyos',
    source_scope TEXT,
    source_key TEXT,
    content_fingerprint TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_feedback_events (
    feedback_id TEXT PRIMARY KEY,
    memory_kind TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS consolidation_jobs (
    job_id TEXT PRIMARY KEY,
    trigger_type TEXT NOT NULL,
    episode_id TEXT,
    state TEXT NOT NULL CHECK (
        state IN ('pending','running','completed','failed','cancelled')
    ),
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS memory_tombstones (
    tombstone_id TEXT PRIMARY KEY,
    scope TEXT NOT NULL CHECK (
        scope IN ('content','subject','source','memory')
    ),
    memory_kind TEXT,
    memory_id TEXT,
    subject_key TEXT,
    source_system TEXT,
    source_id TEXT,
    content_fingerprint TEXT,
    reason TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    created_at TEXT NOT NULL,
    lifted_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',

    CHECK (
        content_fingerprint IS NOT NULL
        OR subject_key IS NOT NULL
        OR source_id IS NOT NULL
        OR memory_id IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_tombstones_active
    ON memory_tombstones(active);
CREATE INDEX IF NOT EXISTS idx_tombstones_fingerprint
    ON memory_tombstones(content_fingerprint);
CREATE INDEX IF NOT EXISTS idx_tombstones_subject
    ON memory_tombstones(subject_key);
CREATE INDEX IF NOT EXISTS idx_tombstones_source
    ON memory_tombstones(source_system, source_id);
CREATE INDEX IF NOT EXISTS idx_tombstones_memory
    ON memory_tombstones(memory_kind, memory_id);
"""



def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _migrate_v1_to_v2(connection: sqlite3.Connection) -> None:
    episode_columns = _table_columns(connection, "memory_episodes")
    fact_columns = _table_columns(connection, "memory_facts")
    procedure_columns = _table_columns(connection, "procedural_memories")

    if "memory_origin" not in episode_columns:
        connection.execute("""
            ALTER TABLE memory_episodes
            ADD COLUMN memory_origin TEXT NOT NULL DEFAULT 'native'
            CHECK(memory_origin IN ('native','external'))
        """)

    additions = (
        ("memory_origin", "TEXT NOT NULL DEFAULT 'native' CHECK(memory_origin IN ('native','external'))"),
        ("source_system", "TEXT NOT NULL DEFAULT 'honeyos'"),
        ("source_scope", "TEXT"),
        ("source_key", "TEXT"),
    )
    for column, definition in additions:
        if column not in fact_columns:
            connection.execute(f"ALTER TABLE memory_facts ADD COLUMN {column} {definition}")
        if column not in procedure_columns:
            connection.execute(f"ALTER TABLE procedural_memories ADD COLUMN {column} {definition}")

    connection.execute("UPDATE schema_meta SET value='2' WHERE key='schema_version'")

def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(DDL)

    row = connection.execute(
        "SELECT value FROM schema_meta WHERE key='schema_version'"
    ).fetchone()

    if row is None:
        connection.execute(
            "INSERT INTO schema_meta(key,value) VALUES('schema_version',?)",
            (str(SCHEMA_VERSION),),
        )
        return

    version = int(row[0])

    if version == 1:
        _migrate_v1_to_v2(connection)
        version = 2

    if version != SCHEMA_VERSION:
        raise RuntimeError(
            f"unsupported cognitive memory schema version: "
            f"{version}; expected {SCHEMA_VERSION}"
        )
