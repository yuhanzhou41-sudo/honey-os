import sqlite3
import pytest

from honeyos.memory import CognitiveMemoryRepository, MemorySuppressedError


def test_db_created(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)
    assert repo.db_path.exists()

    with sqlite3.connect(repo.db_path) as db:
        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    assert "memory_episodes" in tables
    assert "memory_facts" in tables
    assert "memory_tombstones" in tables


def test_episode_round_trip(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)

    episode = repo.create_episode(
        summary="用户开始开发新的记忆架构。",
        source_system="honeyos_test",
        source_key="msg1",
    )

    loaded = repo.get_episode(episode.episode_id)

    assert loaded.summary == episode.summary
    assert loaded.status == "active"


def test_content_suppression_blocks_recreation(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)

    repo.suppress_content("不要重新创建这条内容")

    with pytest.raises(MemorySuppressedError):
        repo.create_episode(summary="不要重新创建这条内容")


def test_subject_suppression_blocks_fact(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)

    repo.suppress_subject("project:honeyos")

    with pytest.raises(MemorySuppressedError):
        repo.create_fact(
            subject="project:honeyos",
            predicate="status",
            object_text="active",
        )


def test_source_suppression_blocks_episode(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)

    repo.suppress_source("deepseek", "conversation-1")

    with pytest.raises(MemorySuppressedError):
        repo.create_episode(
            summary="旧对话",
            memory_origin="external",
            source_system="deepseek",
            source_scope="historical_import",
            source_key="conversation-1",
        )


def test_lift_tombstone_allows_recreation(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)

    tomb = repo.suppress_content("允许以后恢复")
    repo.lift_tombstone(tomb.tombstone_id)

    episode = repo.create_episode(summary="允许以后恢复")
    assert episode.status == "active"


def test_fact_round_trip(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)

    fact = repo.create_fact(
        subject="project:honeyos",
        predicate="status",
        object_text="phase0",
        valid_from="2026-09-24",
    )

    loaded = repo.get_fact(fact.fact_id)

    assert loaded.status == "current"
    assert loaded.object_text == "phase0"


def test_procedural_round_trip(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)

    p = repo.create_procedural(
        key="interaction:concise",
        instruction="回答保持简洁可执行。",
    )

    loaded = repo.get_procedural(p.procedure_id)

    assert loaded.status == "active"
    assert loaded.key == "interaction:concise"


def test_provenance_round_trip(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)

    ep = repo.create_episode(summary="测试事件")

    p = repo.add_provenance(
        memory_kind="episode",
        memory_id=ep.episode_id,
        source_system="test",
        source_type="message",
        source_id="msg-1",
        evidence_quote="测试事件",
    )

    assert p.memory_id == ep.episode_id
    assert p.source_id == "msg-1"


def test_new_database_is_empty(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)

    with repo.connect() as db:
        assert db.execute(
            "SELECT COUNT(*) FROM memory_episodes"
        ).fetchone()[0] == 0

        assert db.execute(
            "SELECT COUNT(*) FROM memory_facts"
        ).fetchone()[0] == 0


def test_existing_episode_forget_is_atomic_and_blocks_recreation(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)

    episode = repo.create_episode(
        summary="这条记忆以后被用户明确要求忘记",
    )

    tombstone = repo.suppress_memory(
        "episode",
        episode.episode_id,
        reason="user_explicit_forget",
    )

    forgotten = repo.get_episode(episode.episode_id)

    assert forgotten.status == "user_suppressed"
    assert tombstone.active is True
    assert tombstone.scope == "memory"
    assert tombstone.memory_kind == "episode"
    assert tombstone.memory_id == episode.episode_id
    assert tombstone.content_fingerprint == episode.content_fingerprint

    with pytest.raises(MemorySuppressedError):
        repo.create_episode(
            summary="这条记忆以后被用户明确要求忘记",
        )


def test_existing_fact_forget_blocks_same_fact_recreation(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)

    fact = repo.create_fact(
        subject="project:test",
        predicate="state",
        object_text="obsolete",
    )

    tombstone = repo.suppress_memory(
        "fact",
        fact.fact_id,
    )

    forgotten = repo.get_fact(fact.fact_id)

    assert forgotten.status == "user_suppressed"
    assert tombstone.memory_kind == "fact"

    with pytest.raises(MemorySuppressedError):
        repo.create_fact(
            subject="project:test",
            predicate="state",
            object_text="obsolete",
        )


def test_existing_procedural_forget_blocks_recreation(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)

    procedure = repo.create_procedural(
        key="interaction:test",
        instruction="采用已经废弃的交互方式",
    )

    tombstone = repo.suppress_memory(
        "procedural",
        procedure.procedure_id,
    )

    forgotten = repo.get_procedural(
        procedure.procedure_id
    )

    assert forgotten.status == "user_suppressed"
    assert tombstone.memory_kind == "procedural"

    with pytest.raises(MemorySuppressedError):
        repo.create_procedural(
            key="interaction:test",
            instruction="采用已经废弃的交互方式",
        )


def test_source_identity_native_and_external_are_distinct(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)
    native = repo.create_episode(summary="HoneyOS 当前聊天形成的记忆", source_system="honeyos")
    external = repo.create_episode(
        summary="DeepSeek 历史导入的事件",
        memory_origin="external",
        source_system="deepseek",
        source_scope="historical_import",
        source_key="conversation-001",
    )
    assert native.memory_origin == "native"
    assert native.source_system == "honeyos"
    assert external.memory_origin == "external"
    assert external.source_system == "deepseek"
    assert external.source_scope == "historical_import"
    assert external.source_key == "conversation-001"


def test_external_memory_cannot_masquerade_as_native(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)
    with pytest.raises(ValueError):
        repo.create_episode(
            summary="错误标记的外来历史",
            memory_origin="native",
            source_system="deepseek",
            source_scope="historical_import",
            source_key="conversation-001",
        )


def test_external_memory_requires_explicit_scope_and_key(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)
    with pytest.raises(ValueError):
        repo.create_episode(summary="缺少范围", memory_origin="external", source_system="deepseek", source_key="conversation-001")
    with pytest.raises(ValueError):
        repo.create_episode(summary="缺少来源键", memory_origin="external", source_system="deepseek", source_scope="historical_import")


def test_external_memory_cannot_use_honeyos_source_namespace(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)
    with pytest.raises(ValueError):
        repo.create_episode(
            summary="来源身份冲突",
            memory_origin="external",
            source_system="honeyos",
            source_scope="historical_import",
            source_key="x",
        )


def test_fact_source_identity_round_trip(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)
    fact = repo.create_fact(
        subject="project:test", predicate="historical_state", object_text="旧阶段",
        memory_origin="external", source_system="deepseek",
        source_scope="historical_import", source_key="conversation-77",
    )
    loaded = repo.get_fact(fact.fact_id)
    assert loaded.memory_origin == "external"
    assert loaded.source_system == "deepseek"
    assert loaded.source_scope == "historical_import"
    assert loaded.source_key == "conversation-77"


def test_procedural_source_identity_round_trip(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)
    p = repo.create_procedural(
        key="interaction:historical", instruction="旧记录中的交互偏好",
        memory_origin="external", source_system="deepseek",
        source_scope="historical_import", source_key="conversation-99",
    )
    loaded = repo.get_procedural(p.procedure_id)
    assert loaded.memory_origin == "external"
    assert loaded.source_system == "deepseek"
    assert loaded.source_scope == "historical_import"
    assert loaded.source_key == "conversation-99"


def test_schema_version_is_source_identity_v2(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)
    with repo.connect() as db:
        version = int(db.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0])
        episode_columns = {row["name"] for row in db.execute("PRAGMA table_info(memory_episodes)")}
        fact_columns = {row["name"] for row in db.execute("PRAGMA table_info(memory_facts)")}
        procedural_columns = {row["name"] for row in db.execute("PRAGMA table_info(procedural_memories)")}
    assert version == 2
    assert "memory_origin" in episode_columns
    required = {"memory_origin", "source_system", "source_scope", "source_key"}
    assert required <= fact_columns
    assert required <= procedural_columns

