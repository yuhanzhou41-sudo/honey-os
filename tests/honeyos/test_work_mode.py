from concurrent.futures import ThreadPoolExecutor
import json
from threading import Event
from unittest.mock import patch

from honeyos.companion.work_mode import active_work, finish_work, start_work, work_turn, workspace
from honeyos.tools import approval
from honeyos.tools.work_tool import work_action


def test_study_skill_submission_requires_approval_and_leaves_candidate_disabled(tmp_path, monkeypatch):
    from honeyos.companion import study_skills

    monkeypatch.setenv("HONEYOS_HOME", str(tmp_path))
    monkeypatch.setenv("HONEYOS_PROJECTS_HOME", str(tmp_path))
    token = work_turn.set(start_work("review-session"))
    request = {"action": "submit_study_skill", "content": json.dumps({
        "name": "Review", "purpose": "Format submitted notes", "heading": "Study",
    })}
    try:
        with patch("honeyos.tools.work_tool.request_single_gateway_approval", return_value=False):
            assert "error" in json.loads(work_action(request))
        assert study_skills.status()["candidates"] == []
        with patch("honeyos.tools.work_tool.request_single_gateway_approval", return_value=True) as gate:
            result = json.loads(work_action(request))
        review = study_skills.status()
        assert result["sha256"] in gate.call_args.args[1]
        assert review["candidates"][0]["digest"] == result["sha256"]
        assert review["active_version"] is None
    finally:
        work_turn.reset(token)


def test_workspace_approval_and_end_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("HONEYOS_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("HONEYOS_PROJECTS_HOME", str(tmp_path / "projects"))
    assert active_work() is None
    identity = start_work("session-a")
    assert start_work("session-b") == identity
    assert workspace(identity[0]).parent == tmp_path / "projects" / "HoneyOS Work"
    token = work_turn.set(identity)
    try:
        request = {"action": "write", "path": "skills/example/SKILL.md", "content": "# Candidate"}
        with patch("honeyos.tools.work_tool.request_single_gateway_approval", return_value=False):
            assert "error" in json.loads(work_action(request))
            assert not workspace(identity[0]).exists()
        with patch("honeyos.tools.work_tool.request_single_gateway_approval", return_value=True) as gate:
            assert "error" in json.loads(work_action({**request, "path": "../escape"}))
            gate.assert_not_called()
            assert "written" in json.loads(work_action(request))
            gate.assert_called_once()
        assert json.loads(work_action({"action": "read", "path": request["path"]}))["content"] == "# Candidate"
        work_action({"action": "summary", "content": "保存了候选 Skill"})
        assert finish_work() == (*identity, "保存了候选 Skill")
        assert "error" in json.loads(work_action(request))
        assert finish_work() is None
    finally:
        work_turn.reset(token)


def test_exact_gateway_approval_rejects_generic_or_persistent_permission():
    session = "work-test"
    ready = Event()
    data = {}
    def notify(payload):
        data.update(payload)
        ready.set()
    def ask():
        token = approval.set_current_session_key(session)
        try:
            return approval.request_single_gateway_approval("write candidate", "safe fixture")
        finally:
            approval.reset_current_session_key(token)

    approval.register_gateway_notify(session, notify)
    try:
        with ThreadPoolExecutor() as worker:
            result = worker.submit(ask)
            try:
                assert ready.wait(5)
                token = data["approval_id"]
                assert approval.resolve_gateway_approval(session, "once") == 0
                assert approval.resolve_gateway_approval(session, "once", approval_id="work-incorrect") == 0
                assert approval.resolve_gateway_approval(session, "always", approval_id=token) == 0
                assert approval.resolve_gateway_approval(session, "once", approval_id=token) == 1
                assert result.result(timeout=3)
            finally:
                if data.get("approval_id"):
                    approval.resolve_gateway_approval(session, "deny", approval_id=data["approval_id"])
    finally:
        approval.unregister_gateway_notify(session)


def test_python_execution_has_read_only_candidate_no_host_or_credentials(tmp_path, monkeypatch):
    import shutil
    import pytest
    from honeyos.tools.work_tool import _run_python

    if not shutil.which("bwrap"):
        pytest.skip("requires bubblewrap")
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    monkeypatch.setenv("HONEYOS_WORK_SECRET_FIXTURE", "must not escape")
    (candidate / "check.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        "assert not Path('/mnt/c').exists()\n"
        "assert not Path('/mnt/d').exists()\n"
        "assert not Path('/mnt/e').exists()\n"
        "assert not Path('/home').exists()\n"
        "assert 'HONEYOS_WORK_SECRET_FIXTURE' not in os.environ\n"
        "try:\n"
        "    Path('/work/unapproved.txt').write_text('no')\n"
        "except OSError:\n"
        "    pass\n"
        "else:\n"
        "    raise AssertionError('candidate bind is writable')\n"
        "print('sandbox ok')\n",
        encoding="utf-8",
    )
    result = _run_python(candidate, "./check.py")
    assert result["exit_code"] == 0, result
    assert "sandbox ok" in result["output"]


def test_work_mode_exposes_work_actions_planning_and_questions():
    from honeyos.model_tools import get_tool_definitions

    tools = get_tool_definitions(enabled_toolsets=["companion_work", "todo", "clarify"], quiet_mode=True)
    names = {tool["function"]["name"] for tool in tools}
    assert {"work_action", "todo", "clarify"} <= names
    assert not names.intersection({"terminal", "execute_code", "write_file", "skill_manage"})
