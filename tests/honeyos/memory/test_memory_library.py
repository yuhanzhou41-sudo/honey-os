from honeyos.memory import CognitiveMemoryRepository
from honeyos.memory.library import CognitiveMemoryLibrary, history_partition


def _add(repo, *, summary, eid, suppressed=False):
    episode = repo.create_episode(
        episode_id=eid,
        episode_type="historical_external",
        summary=summary,
        occurred_at="2026-01-02T03:04:05+08:00",
        memory_origin="external",
        source_system="deepseek",
        source_scope="historical_import",
        source_key="source-" + eid,
        metadata={
            "raw_time": "raw",
            "evidence_time_start": "2026-01-01T03:04:05+08:00",
            "evidence_time_end": "2026-01-02T03:04:05+08:00",
        },
    )
    repo.add_provenance(
        memory_kind="episode",
        memory_id=episode.episode_id,
        source_system="deepseek",
        source_type="historical_message_evidence",
        source_id="conversation-1",
        evidence_quote="证据",
    )
    if suppressed:
        repo.suppress_memory("episode", episode.episode_id)
    return episode


def test_history_partition():
    assert history_partition("【虚构角色扮演】继续剧情")[0] == "roleplay"
    assert history_partition("用户完善小说世界观与角色设定")[0] == "fiction"
    assert history_partition("HoneyOS 项目部署和 API 开发")[0] == "project"
    assert history_partition("论文研究和考试复习计划")[0] == "study_research"
    assert history_partition("用户明确偏好共同完成有意义的事情")[0] == "personal"
    assert history_partition("无法归入上述类别的历史片段")[0] == "other"


def test_list_historical_only_external_and_hides_suppressed(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path / "memory.sqlite")
    _add(repo, summary="HoneyOS 项目开发", eid="me_external")
    _add(repo, summary="【虚构角色扮演】剧情", eid="me_suppressed", suppressed=True)
    repo.create_episode(
        episode_id="me_native",
        summary="native",
        memory_origin="native",
        source_system="honeyos",
    )
    page = CognitiveMemoryLibrary(repo).list_historical()
    assert page.total == 1
    assert page.items[0]["id"] == "me_external"


def test_filter_search_and_pagination(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path / "memory.sqlite")
    _add(repo, summary="【虚构角色扮演】A", eid="me_a")
    _add(repo, summary="【虚构角色扮演】B", eid="me_b")
    _add(repo, summary="HoneyOS 项目开发", eid="me_c")
    lib = CognitiveMemoryLibrary(repo)
    page = lib.list_historical(partition="roleplay", limit=1, offset=1)
    assert page.total == 2
    assert len(page.items) == 1
    search = lib.list_historical(query="honeyos")
    assert search.total == 1
    assert search.items[0]["id"] == "me_c"


def test_detail_includes_provenance_and_time_span(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path / "memory.sqlite")
    _add(repo, summary="论文研究和考试复习计划", eid="me_a")
    item = CognitiveMemoryLibrary(repo).get_historical("me_a")
    assert item["time_start"] == "2026-01-01T03:04:05+08:00"
    assert item["time_end"] == "2026-01-02T03:04:05+08:00"
    assert item["provenance"][0]["evidence_quote"] == "证据"

def test_edit_preserves_revision_and_provenance(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path / "memory.sqlite")
    _add(repo, summary="原始内容", eid="me_edit")
    lib = CognitiveMemoryLibrary(repo)
    before = lib.get_historical("me_edit")
    assert len(before["provenance"]) == 1
    updated = lib.update_historical("me_edit", "修正后的内容")
    assert updated["summary"] == "修正后的内容"
    assert len(updated["provenance"]) == 1
    edits = [x for x in updated["revisions"] if x["event_type"] == "user_edit"]
    assert len(edits) == 1
    assert edits[0]["payload"]["old_summary"] == "原始内容"
    assert edits[0]["payload"]["new_summary"] == "修正后的内容"


def test_trash_hides_from_library_and_restore_reactivates(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path / "memory.sqlite")
    _add(repo, summary="HoneyOS 项目开发", eid="me_trash")
    lib = CognitiveMemoryLibrary(repo)
    trashed = lib.move_to_trash("me_trash")
    assert trashed["status"] == "user_suppressed"
    assert lib.list_historical().total == 0
    assert lib.list_trash().total == 1
    restored = lib.restore_from_trash("me_trash")
    assert restored["status"] == "active"
    assert lib.list_trash().total == 0
    assert lib.list_historical().total == 1
    with repo.connect() as db:
        active = db.execute("SELECT COUNT(*) FROM memory_tombstones WHERE active=1 AND scope='memory' AND memory_kind='episode' AND memory_id='me_trash'").fetchone()[0]
    assert active == 0


def test_cannot_edit_memory_in_recycle_bin(tmp_path):
    import pytest
    repo = CognitiveMemoryRepository(tmp_path / "memory.sqlite")
    _add(repo, summary="待删除", eid="me_locked")
    lib = CognitiveMemoryLibrary(repo)
    lib.move_to_trash("me_locked")
    with pytest.raises(ValueError):
        lib.update_historical("me_locked", "不应该成功")

def test_permanent_delete_erases_payload_and_keeps_source_tombstone(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path / "memory.sqlite")
    _add(repo, summary="需要永久删除的历史记忆", eid="me_perm")
    lib = CognitiveMemoryLibrary(repo)
    lib.update_historical("me_perm", "编辑过的历史记忆")
    lib.move_to_trash("me_perm")
    result = lib.permanently_delete_from_trash("me_perm")
    assert result["deleted"] is True

    with repo.connect() as db:
        assert db.execute(
            "SELECT COUNT(*) FROM memory_episodes WHERE episode_id='me_perm'"
        ).fetchone()[0] == 0
        assert db.execute(
            "SELECT COUNT(*) FROM memory_provenance "
            "WHERE memory_kind='episode' AND memory_id='me_perm'"
        ).fetchone()[0] == 0
        assert db.execute(
            "SELECT COUNT(*) FROM memory_feedback_events "
            "WHERE memory_kind='episode' AND memory_id='me_perm'"
        ).fetchone()[0] == 0
        assert db.execute(
            "SELECT COUNT(*) FROM memory_tombstones "
            "WHERE scope='memory' AND memory_kind='episode' AND memory_id='me_perm'"
        ).fetchone()[0] == 0

        source_tombstone = db.execute(
            '''
            SELECT scope,source_system,source_id,reason,active,content_fingerprint
            FROM memory_tombstones
            WHERE scope='source'
              AND source_system='deepseek'
              AND source_id='source-me_perm'
              AND active=1
            '''
        ).fetchone()

    assert source_tombstone is not None
    assert source_tombstone["reason"] == "user_permanent_delete"
    assert source_tombstone["content_fingerprint"] is None


def test_permanent_delete_requires_recycle_bin(tmp_path):
    import pytest
    repo = CognitiveMemoryRepository(tmp_path / "memory.sqlite")
    _add(repo, summary="仍然活跃", eid="me_active_perm")
    lib = CognitiveMemoryLibrary(repo)
    with pytest.raises(ValueError):
        lib.permanently_delete_from_trash("me_active_perm")


def test_permanent_delete_source_tombstone_blocks_reimport(tmp_path):
    import pytest
    from honeyos.memory.repository import MemorySuppressedError

    repo = CognitiveMemoryRepository(tmp_path / "memory.sqlite")
    _add(repo, summary="原始历史", eid="me_block")
    lib = CognitiveMemoryLibrary(repo)
    lib.move_to_trash("me_block")
    lib.permanently_delete_from_trash("me_block")

    with pytest.raises(MemorySuppressedError):
        repo.create_episode(
            episode_id="me_block_again",
            episode_type="historical_external",
            summary="即使正文改变也不能用同一 source_key 复活",
            memory_origin="external",
            source_system="deepseek",
            source_scope="historical_import",
            source_key="source-me_block",
        )
