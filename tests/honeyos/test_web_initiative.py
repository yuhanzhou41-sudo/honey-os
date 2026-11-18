from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from honeyos.companion import web_initiative
from honeyos.gateway.config import Platform
from honeyos.gateway.session import SessionSource


@pytest.fixture
def pilot(monkeypatch, tmp_path):
    monkeypatch.setenv("HONEYOS_HOME", str(tmp_path))
    now = datetime(2026, 11, 18, 12, tzinfo=timezone(timedelta(hours=8)))
    channel = SimpleNamespace(
        source=SessionSource(platform=Platform.API_SERVER, chat_id="local-owner", chat_type="dm").to_dict(),
        last_user_message_at=now - timedelta(hours=1),
    )
    db = SimpleNamespace(resolve_resume_session_id=lambda session_id: session_id)
    adapter = SimpleNamespace(
        _ensure_session_db_async=AsyncMock(return_value=db), _companion_stream_controls={},
        send=AsyncMock(return_value=SimpleNamespace(success=True)),
    )
    runner = SimpleNamespace(
        adapters={Platform.API_SERVER: adapter}, _running_agents={},
        _session_key_for_source=lambda _source: "owner",
        session_store=SimpleNamespace(peek_session_id=lambda _key: "session"),
    )
    store = SimpleNamespace(latest_channel=Mock(return_value=channel))
    decision = Mock(return_value="我想接着聊之前的想法")
    writer = AsyncMock(return_value="我刚才又想起了我们之前聊过的事。")
    monkeypatch.setattr(web_initiative, "_context", lambda *_: {"mood": {"curiosity": 0.5}})
    monkeypatch.setattr(web_initiative, "_decision", decision)
    monkeypatch.setattr(web_initiative, "_write_message", writer)
    return now, channel, adapter, runner, store, decision, writer


@pytest.mark.asyncio
async def test_only_positive_hourly_decision_reaches_main_and_local_chat(pilot):
    now, _, adapter, runner, store, decision, writer = pilot
    assert not await web_initiative.run_hourly(runner, store, now)
    decision.assert_not_called()
    web_initiative.set_preference(True)

    decision.return_value = None
    assert not await web_initiative.run_hourly(runner, store, now)
    writer.assert_not_awaited()
    assert not await web_initiative.run_hourly(runner, store, now + timedelta(minutes=59))
    assert decision.call_count == 1

    decision.return_value = "我想联系"
    assert await web_initiative.run_hourly(runner, store, now + timedelta(hours=1))
    writer.assert_awaited_once()
    adapter.send.assert_awaited_once_with("session", writer.return_value)
    store.latest_channel.assert_called_with(platform=Platform.API_SERVER.value)


@pytest.mark.asyncio
async def test_night_checks_every_three_hours_without_silence(pilot):
    now, _, adapter, runner, store, _, _ = pilot
    night = now.replace(hour=23)
    web_initiative.set_preference(True)

    assert await web_initiative.run_hourly(runner, store, night)
    assert not await web_initiative.run_hourly(runner, store, night + timedelta(hours=2))
    assert await web_initiative.run_hourly(runner, store, night + timedelta(hours=3))
    assert adapter.send.await_count == 2


@pytest.mark.asyncio
async def test_recent_or_live_chat_skips_check_and_disabling_cancels_delivery(pilot):
    now, channel, adapter, runner, store, decision, writer = pilot
    web_initiative.set_preference(True)
    channel.last_user_message_at = now - timedelta(minutes=5)
    assert not await web_initiative.run_hourly(runner, store, now)
    channel.last_user_message_at = now - timedelta(hours=1)
    adapter._companion_stream_controls["current"] = {"session_id": "session"}
    assert not await web_initiative.run_hourly(runner, store, now)
    decision.assert_not_called()
    adapter._companion_stream_controls.clear()

    async def switch_off(*_):
        web_initiative.set_preference(False)
        return "此消息不应送达"

    writer.side_effect = switch_off
    assert not await web_initiative.run_hourly(runner, store, now)
    writer.assert_awaited_once()
    adapter.send.assert_not_awaited()
