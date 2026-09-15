from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest

from honeyos.companion.diary import DiaryStore


def test_diary_store_keeps_authors_separate_and_orders_dates(tmp_path):
    store = DiaryStore(tmp_path)
    older = store.create_entry(
        author="user", entry_date="2026-09-14", content="昨天的记录"
    )
    assistant = store.create_entry(
        author="assistant", entry_date="2026-09-15", content="今天的回应"
    )
    user = store.create_entry(
        author="user", entry_date="2026-09-15", content="今天的记录"
    )

    entries = store.list_entries()

    assert {entry.id for entry in entries} == {older.id, assistant.id, user.id}
    assert entries[-1].id == older.id
    assert {entry.author for entry in entries[:2]} == {"user", "assistant"}


def test_only_one_assistant_entry_is_allowed_per_day(tmp_path):
    store = DiaryStore(tmp_path)
    store.create_entry(
        author="assistant", entry_date="2026-09-15", content="第一篇"
    )

    with pytest.raises(ValueError, match="assistant_diary_already_exists"):
        store.create_entry(
            author="assistant", entry_date="2026-09-15", content="第二篇"
        )


def test_user_cannot_modify_or_delete_assistant_entry(tmp_path):
    store = DiaryStore(tmp_path)
    assistant = store.create_entry(
        author="assistant", entry_date="2026-09-15", content="AI 日记"
    )

    assert store.update_user_entry(assistant.id, content="篡改") is None
    assert store.delete_user_entry(assistant.id) is False


def test_user_entry_can_be_updated_and_deleted(tmp_path):
    store = DiaryStore(tmp_path)
    entry = store.create_entry(
        author="user", entry_date="2026-09-15", content="初稿"
    )

    updated = store.update_user_entry(entry.id, content="修改后")

    assert updated is not None
    assert updated.content == "修改后"
    assert store.delete_user_entry(entry.id) is True
    assert store.list_entries() == ()


def test_diary_permissions_default_private_from_memory_and_enforce_view(tmp_path):
    store = DiaryStore(tmp_path)
    default = store.create_entry(
        author="user", entry_date="2026-09-15", content="默认权限"
    )
    remembered = store.create_entry(
        author="user",
        entry_date="2026-09-15",
        content="希望记住",
        allow_ai_view=False,
        allow_memory=True,
    )

    assert default.allow_ai_view is True
    assert default.allow_memory is False
    assert remembered.allow_ai_view is True
    assert remembered.allow_memory is True

    hidden = store.update_user_entry(
        remembered.id, allow_ai_view=False
    )
    assert hidden is not None
    assert hidden.allow_ai_view is False
    assert hidden.allow_memory is False


def test_daily_diary_claim_excludes_entries_without_view_permission(tmp_path):
    store = DiaryStore(tmp_path)
    store.create_entry(
        author="user",
        entry_date="2026-09-15",
        content="不要给 AI 看",
        allow_ai_view=False,
    )
    store.create_entry(
        author="user",
        entry_date="2026-09-15",
        content="可以给 AI 看",
        allow_ai_view=True,
    )

    claimed = store.claim_user_entries_for_day("2026-09-15")

    assert [entry.content for entry in claimed] == ["可以给 AI 看"]


def test_memory_entries_form_one_versioned_bucket_per_date(tmp_path):
    store = DiaryStore(tmp_path)
    first = store.create_entry(
        author="user",
        entry_date="2026-09-15",
        content="现实事件一",
        allow_memory=True,
    )
    store.create_entry(
        author="user",
        entry_date="2026-09-15",
        content="现实事件二",
        allow_memory=True,
    )

    pending = store.pending_memory_buckets()
    assert len(pending) == 1
    assert pending[0].weight == 3
    assert "现实事件一" in pending[0].content
    assert "现实事件二" in pending[0].content

    store.mark_memory_buckets_processed(pending)
    assert store.pending_memory_buckets() == ()

    store.update_user_entry(first.id, content="现实事件一已更新")
    changed = store.pending_memory_buckets()
    assert len(changed) == 1
    assert changed[0].version != pending[0].version


@pytest.mark.parametrize("value", ["", "   ", "x" * 20_001])
def test_diary_content_is_validated(tmp_path, value):
    with pytest.raises(ValueError):
        DiaryStore(tmp_path).create_entry(
            author="user", entry_date="2026-09-15", content=value
        )


def test_user_entries_are_claimed_only_once_per_day_and_survive_restart(tmp_path):
    store = DiaryStore(tmp_path)
    store.create_entry(author="user", entry_date="2026-09-15", content="新日记")
    now = datetime.now(timezone.utc)

    first = store.claim_user_entries_for_day("2026-09-15", now=now)
    restarted = DiaryStore(tmp_path)
    second = restarted.claim_user_entries_for_day("2026-09-15", now=now + timedelta(hours=1))

    assert [entry.content for entry in first] == ["新日记"]
    assert second == ()


def test_new_user_change_waits_for_next_daily_claim(tmp_path):
    store = DiaryStore(tmp_path)
    first_entry = store.create_entry(author="user", entry_date="2026-09-15", content="第一篇")
    first_now = datetime.now(timezone.utc)
    assert store.claim_user_entries_for_day("2026-09-15", now=first_now)

    store.update_user_entry(first_entry.id, content="当天领取后的修改")
    assert store.claim_user_entries_for_day("2026-09-15", now=first_now + timedelta(hours=1)) == ()
    next_day = store.claim_user_entries_for_day(
        "2026-09-16", now=first_now + timedelta(days=1)
    )

    assert [entry.content for entry in next_day] == ["当天领取后的修改"]


def test_assistant_generation_lease_blocks_duplicates(tmp_path):
    store = DiaryStore(tmp_path)
    now = datetime.now(timezone.utc)

    assert store.begin_assistant_generation("2026-09-15", now=now) is True
    assert store.begin_assistant_generation(
        "2026-09-15", now=now + timedelta(minutes=30)
    ) is False


def test_stale_or_failed_assistant_generation_can_retry(tmp_path):
    store = DiaryStore(tmp_path)
    now = datetime.now(timezone.utc)
    assert store.begin_assistant_generation("2026-09-15", now=now)
    assert store.begin_assistant_generation(
        "2026-09-15", now=now + timedelta(hours=2)
    )
    store.fail_assistant_generation("2026-09-15", "temporary failure")
    assert store.begin_assistant_generation(
        "2026-09-15", now=now + timedelta(hours=3)
    )


def test_existing_assistant_entry_permanently_blocks_generation(tmp_path):
    store = DiaryStore(tmp_path)
    entry = store.create_entry(
        author="assistant", entry_date="2026-09-15", content="已经完成"
    )
    store.finish_assistant_generation("2026-09-15", entry.id)

    assert store.begin_assistant_generation("2026-09-15") is False


def test_generation_status_records_completion_and_user_read_count(tmp_path):
    store = DiaryStore(tmp_path)
    store.create_entry(
        author="user", entry_date="2026-09-15", content="给今晚看的日记"
    )
    assert store.begin_assistant_generation("2026-09-15")
    assert len(store.claim_user_entries_for_day("2026-09-15")) == 1
    assistant = store.create_entry(
        author="assistant", entry_date="2026-09-15", content="今晚写下的内容"
    )
    store.finish_assistant_generation("2026-09-15", assistant.id)

    status = store.generation_status("2026-09-15")
    assert status["status"] == "completed"
    assert status["completed_at"]
    assert status["assistant_entry_id"] == assistant.id
    assert status["user_read_count"] == 1
