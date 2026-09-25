from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")

def test_api_server_proactive_send_contract_is_present():
    src = _read("honeyos/gateway/platforms/api_server.py")
    assert 'display_kind="proactive"' in src
    assert '"source": "proactive_delivery"' in src
    assert "db.append_message" in src
    assert "self._notify_companion_message(resolved_id, message_id)" in src
    assert "API server uses HTTP request/response, not send()" not in src

def test_api_server_session_message_sse_contract_is_present():
    src = _read("honeyos/gateway/platforms/api_server.py")
    assert "/api/sessions/{session_id}/message-events" in src
    assert "async def _handle_session_message_events(" in src
    assert "honeyos.session.message" in src
    assert "_companion_message_subscribers" in src

def test_scheduler_does_not_bypass_api_server_adapter_send():
    src = _read("honeyos/scheduler/scheduler.py")
    assert "API_SERVER_CRON_DIRECT_DELIVERY_V1" not in src
    assert "API_SERVER_CRON_DIRECT_DELIVERY_V2" not in src

def test_frontend_watches_durable_session_message_events():
    chat_api = _read("frontend/src/api/chat.ts")
    chat_page = _read("frontend/src/features/chat/ChatPage.tsx")
    store = _read("frontend/src/runtime/honey-store.ts")
    assert "watchSessionMessages" in chat_api
    assert "/message-events" in chat_api
    assert "await watchSessionMessages({" in chat_page
    assert "fetchCompanionMessages" in chat_page
    assert "mergeTimelineMessages" in chat_page
    assert "mergeTimelineMessages:" in store

def test_fixed_reminder_clean_zero_model_contract_is_present():
    src = _read("honeyos/scheduler/scheduler.py")
    assert 'job.get("task_kind") == "fixed_reminder"' in src
    assert "zero-model execution; delivering stored text" in src
    assert "delivery_content = content" in src


def test_live_watcher_starts_without_session_key():
    page = _read("frontend/src/features/chat/ChatPage.tsx")
    api = _read("frontend/src/api/chat.ts")
    watch_pos = page.index("await watchSessionMessages({")
    start = page.rfind("useEffect(() => {", 0, watch_pos)
    end = page.index("}, [sessionId, sessionKey, mergeTimelineMessages]);", watch_pos)
    effect = page[start:end]
    assert "if (!sessionId) return;" in effect
    assert "if (!sessionId || !sessionKey) return;" not in effect
    assert "sessionKey?: string;" in api
