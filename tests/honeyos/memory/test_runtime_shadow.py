from __future__ import annotations

import json
from pathlib import Path

from honeyos.memory.repository import CognitiveMemoryRepository
from honeyos.memory.runtime_shadow import CognitiveMemoryShadowRetriever


def _repo(tmp_path: Path) -> CognitiveMemoryRepository:
    return CognitiveMemoryRepository(db_path=tmp_path / "cognitive.sqlite")


def _add(repo, *, eid: str, summary: str, source_key: str | None = None):
    return repo.create_episode(
        episode_id=eid,
        episode_type="historical_external",
        summary=summary,
        memory_origin="external",
        source_system="deepseek",
        source_scope="historical_import",
        source_key=source_key or f"source-{eid}",
    )


def test_shadow_selects_relevant_external_memory_without_prompt_payload(tmp_path):
    repo = _repo(tmp_path)
    _add(repo, eid="me_honey", summary="用户持续开发 HoneyOS Study System 和记忆系统。")
    _add(repo, eid="me_other", summary="用户讨论过普通饮食安排。")
    retriever = CognitiveMemoryShadowRetriever(
        repo,
        audit_path=tmp_path / "shadow.jsonl",
    )

    result = retriever.retrieve("HoneyOS 记忆系统现在做到哪里了？", write_audit=False)

    assert result.prompt_injection is False
    assert result.selected
    assert result.selected[0].id == "me_honey"
    assert result.total_char_cost <= 900


def test_shadow_excludes_active_source_tombstone(tmp_path):
    repo = _repo(tmp_path)
    _add(repo, eid="me_dead", summary="西游记童年故事记录", source_key="dead-source")
    with repo.connect() as db:
        db.execute(
            """
            INSERT INTO memory_tombstones(
                tombstone_id,scope,memory_kind,memory_id,subject_key,
                source_system,source_id,content_fingerprint,reason,active,
                created_at,lifted_at,metadata_json
            )
            VALUES(
                'mt_dead','source',NULL,NULL,NULL,
                'deepseek','dead-source',NULL,'user_permanent_delete',1,
                '2026-09-26T00:00:00+00:00',NULL,'{}'
            )
            """
        )

    result = CognitiveMemoryShadowRetriever(repo).retrieve(
        "西游记故事",
        write_audit=False,
    )
    assert all(item.id != "me_dead" for item in result.selected)


def test_shadow_blocks_roleplay_without_namespace_signal(tmp_path):
    repo = _repo(tmp_path)
    _add(
        repo,
        eid="me_rp",
        summary="角色扮演：骑士与王子在宫廷剧情中继续对话。",
    )
    retriever = CognitiveMemoryShadowRetriever(repo)

    result = retriever.retrieve("我以前谈到过骑士吗？", write_audit=False)

    assert all(item.id != "me_rp" for item in result.selected)
    assert any(
        item.id == "me_rp" and item.reason == "namespace_mismatch"
        for item in result.rejected
    )


def test_shadow_allows_roleplay_when_turn_explicitly_requests_it(tmp_path):
    repo = _repo(tmp_path)
    _add(
        repo,
        eid="me_rp",
        summary="角色扮演：骑士与王子在宫廷剧情中继续对话。",
    )

    result = CognitiveMemoryShadowRetriever(repo).retrieve(
        "找一下以前角色扮演里的骑士剧情",
        write_audit=False,
    )

    assert any(item.id == "me_rp" for item in result.selected)


def test_shadow_enforces_result_and_character_budget(tmp_path):
    repo = _repo(tmp_path)
    for idx in range(6):
        _add(
            repo,
            eid=f"me_{idx}",
            summary=("HoneyOS 记忆系统 " + str(idx) + " ") * 40,
        )
    result = CognitiveMemoryShadowRetriever(
        repo,
        max_results=3,
        char_budget=120,
        max_preview_per_item=80,
    ).retrieve("HoneyOS 记忆系统", write_audit=False)

    assert len(result.selected) <= 3
    assert result.total_char_cost <= 120
    assert sum(item.char_cost for item in result.selected) == result.total_char_cost


def test_shadow_audit_is_jsonl_and_marks_no_prompt_injection(tmp_path):
    repo = _repo(tmp_path)
    _add(repo, eid="me_one", summary="HoneyOS 项目记忆")
    audit = tmp_path / "shadow.jsonl"
    retriever = CognitiveMemoryShadowRetriever(repo, audit_path=audit)

    retriever.retrieve(
        "HoneyOS 项目",
        session_id="session-1",
        turn_id="turn-1",
        write_audit=True,
    )

    rows = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["mode"] == "shadow"
    assert rows[0]["prompt_injection"] is False
    assert rows[0]["session_id"] == "session-1"
    assert rows[0]["turn_id"] == "turn-1"

def test_shadow_subject_terms_outrank_roleplay_query_scaffolding(tmp_path):
    repo = _repo(tmp_path)
    _add(repo, eid="me_vampire", summary="角色扮演：吸血鬼薇缇与洛佐继续讨论转化后的剧情。")
    _add(repo, eid="me_generic_rp", summary="角色扮演：骑士与王子在宫廷中继续对话。")

    result = CognitiveMemoryShadowRetriever(repo).retrieve(
        "找一下我以前角色扮演里和吸血鬼有关的剧情",
        write_audit=False,
    )

    assert result.selected
    assert result.selected[0].id == "me_vampire"
    assert all(item.id != "me_generic_rp" for item in result.selected)


def test_shadow_general_personal_query_blocks_fiction_misclassified_by_ui(tmp_path):
    repo = _repo(tmp_path)
    _add(repo, eid="me_real", summary="用户小时候的家庭关系中经常与妹妹一起生活。")
    _add(
        repo,
        eid="me_fiction_personal_bucket",
        summary="用户为云肆安与马亦钧设计了长期且复杂的虚构友情关系；角色出身富裕家庭，家庭关系复杂。",
    )
    _add(
        repo,
        eid="me_worldbook",
        summary="用户制作世界书，包含角色JSON、人物关系和家庭关系等字段。",
    )

    result = CognitiveMemoryShadowRetriever(repo).retrieve(
        "我小时候家里的家庭关系如何",
        write_audit=False,
    )

    assert any(item.id == "me_real" for item in result.selected)
    assert all(item.id != "me_fiction_personal_bucket" for item in result.selected)
    assert all(item.id != "me_worldbook" for item in result.selected)
    rejected_ids = {
        item.id for item in result.rejected if item.reason == "namespace_mismatch"
    }
    assert "me_fiction_personal_bucket" in rejected_ids
    assert "me_worldbook" in rejected_ids


def test_shadow_honeyos_query_does_not_select_generic_system_collision(tmp_path):
    repo = _repo(tmp_path)
    _add(repo, eid="me_honey", summary="用户使用 HoneyOS 开发长期记忆系统与学习系统。")
    _add(repo, eid="me_generic", summary="用户讨论某个抽象系统目前的哲学意义。")

    result = CognitiveMemoryShadowRetriever(repo).retrieve(
        "HoneyOS的系统目前开发到哪个阶段了",
        write_audit=False,
    )

    assert result.selected
    assert result.selected[0].id == "me_honey"
    assert all(item.id != "me_generic" for item in result.selected)

def test_shadow_honeyos_exact_term_beats_generic_system_words(tmp_path):
    repo = _repo(tmp_path)
    _add(repo, eid="me_honey", summary="用户使用 HoneyOS 开发长期记忆系统。")
    _add(repo, eid="me_generic", summary="用户讨论某个抽象系统与人生意义。")

    result = CognitiveMemoryShadowRetriever(repo).retrieve(
        "HoneyOS的系统目前开发到哪个阶段了",
        write_audit=False,
    )

    assert result.selected
    assert result.selected[0].id == "me_honey"
    assert all(item.id != "me_generic" for item in result.selected)


def test_shadow_blocks_titled_fiction_and_character_design_from_general_family_query(tmp_path):
    repo = _repo(tmp_path)
    _add(
        repo,
        eid="me_real",
        summary="用户小时候受到学校和家庭评价体系影响，也提到与妹妹一起生活。",
    )
    _add(
        repo,
        eid="me_title_fiction",
        summary="在《从祭品到神祠主理人》中，角色的家庭关系与神力规则彼此关联。",
    )
    _add(
        repo,
        eid="me_character_design",
        summary="用户为云肆安设定了朋友马亦钧，包含复杂家庭关系与人物经历。",
    )

    result = CognitiveMemoryShadowRetriever(repo).retrieve(
        "我小时候家里的家庭关系如何",
        write_audit=False,
    )

    assert any(item.id == "me_real" for item in result.selected)
    assert all(item.id != "me_title_fiction" for item in result.selected)
    assert all(item.id != "me_character_design" for item in result.selected)
    rejected = {item.id: item.reason for item in result.rejected}
    assert rejected.get("me_title_fiction") == "namespace_mismatch"
    assert rejected.get("me_character_design") == "namespace_mismatch"
