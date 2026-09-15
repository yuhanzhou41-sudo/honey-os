from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from honeyos.companion.diary import DiaryStore
from honeyos.companion.diary_automation import (
    DIARY_MAX_OUTPUT_TOKENS,
    build_diary_messages,
    generate_diary_entry,
    next_generation_at,
    startup_target_date,
)
from honeyos.companion.distillation import DistillationSettings, MemoryDistiller


def test_clock_uses_2330_and_catches_up_yesterday_before_boundary():
    before = datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc)
    after = datetime(2026, 9, 16, 23, 40, tzinfo=timezone.utc)
    assert startup_target_date(before).isoformat() == "2026-09-15"
    assert startup_target_date(after).isoformat() == "2026-09-16"
    assert next_generation_at(before).hour == 23
    assert next_generation_at(before).minute == 30
    assert next_generation_at(after).date().isoformat() == "2026-09-17"


def test_prompt_is_open_but_keeps_imagination_out_of_facts(tmp_path):
    entry = DiaryStore(tmp_path).create_entry(author="user", entry_date="2026-09-15", content="今天下雨")
    messages = build_diary_messages(target_date="2026-09-15", companion_profile={}, user_entries=(entry,), transcript=[])
    assert "open creative space" in messages[0]["content"]
    assert "distinguish imagination" in messages[0]["content"]
    assert "今天下雨" in messages[1]["content"]


@pytest.mark.asyncio
async def test_generation_caps_tokens_and_never_reads_assistant_diary(tmp_path):
    store = DiaryStore(tmp_path)
    store.create_entry(author="assistant", entry_date="2026-09-14", content="SECRET OLD AI DIARY")
    store.create_entry(author="user", entry_date="2026-09-15", content="用户新日记")
    captured = {}

    async def fake_call(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="自由写下的一页"))])

    result = await generate_diary_entry(home=tmp_path, target_date="2026-09-15", companion_profile={}, transcript=[], main_runtime={}, call_llm=fake_call)
    assert result and result.content == "自由写下的一页"
    assert captured["max_tokens"] == DIARY_MAX_OUTPUT_TOKENS == 3000
    assert "用户新日记" in str(captured["messages"])
    assert "SECRET OLD AI DIARY" not in str(captured["messages"])


@pytest.mark.asyncio
async def test_generation_failure_releases_lease_for_retry(tmp_path):
    async def fail(**kwargs):
        raise RuntimeError("temporary")

    with pytest.raises(RuntimeError):
        await generate_diary_entry(home=tmp_path, target_date="2026-09-15", companion_profile={}, transcript=[], main_runtime={}, call_llm=fail)
    assert DiaryStore(tmp_path).begin_assistant_generation("2026-09-15") is True


def test_diary_date_adds_three_units_to_existing_memory_trigger(tmp_path):
    DiaryStore(tmp_path).create_entry(
        author="user",
        entry_date="2026-09-15",
        content="允许进入长期记忆的现实记录",
        allow_memory=True,
    )
    distiller = MemoryDistiller(
        tmp_path,
        settings=DistillationSettings(trigger_messages=5),
    )
    messages = [
        {"_row_id": 1, "role": "user", "content": "第一条聊天"},
        {"_row_id": 2, "role": "assistant", "content": "第二条聊天"},
    ]

    job = distiller._prepare(
        lane_key="agent:main:api_server:dm:local-owner",
        session_id="session-1",
        messages=messages,
        reason="periodic",
        now=datetime.now(timezone.utc),
    )

    assert job is not None
    assert len(job.diary_buckets) == 1
    diary_message = next(
        message for message in job.messages if message.get("evidence_type") == "user_diary"
    )
    assert diary_message["entry_date"] == "2026-09-15"
    assert diary_message["_row_id"] < 0
