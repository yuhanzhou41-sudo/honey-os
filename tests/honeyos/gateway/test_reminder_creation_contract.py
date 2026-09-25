from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")

def test_jobs_persists_fixed_reminder_fields():
    src = _read("honeyos/scheduler/jobs.py")
    assert "task_kind: Optional[str] = None" in src
    assert "reminder_text: Optional[str] = None" in src
    assert '"task_kind": normalized_task_kind' in src
    assert '"reminder_text": normalized_reminder_text or None' in src

def test_cronjob_tool_exposes_and_forwards_fixed_reminder():
    src = _read("honeyos/tools/cronjob_tools.py")
    assert '"task_kind": {' in src
    assert '"reminder_text": {' in src
    assert "task_kind=_task_kind" in src
    assert "reminder_text=_reminder_text or None" in src
    assert 'task_kind=args.get("task_kind")' in src
    assert 'reminder_text=args.get("reminder_text")' in src
    assert '"task_kind": job.get("task_kind")' in src
    assert '"reminder_text": job.get("reminder_text")' in src

def test_simple_reminder_schema_forces_fixed_lane():
    src = _read("honeyos/tools/cronjob_tools.py")
    assert "you MUST create task_kind='fixed_reminder'" in src
    assert "Do not use prompt/skills for this case" in src

def test_scheduler_fixed_lane_still_present():
    src = _read("honeyos/scheduler/scheduler.py")
    assert 'job.get("task_kind") == "fixed_reminder"' in src
    assert "zero-model execution; delivering stored text" in src

def test_frontend_sse_parser_uses_real_newline_escapes():
    src = _read("frontend/src/api/chat.ts")
    correct = r'replaceAll("\r\n", "\n").split("\n\n")'
    broken = r'replaceAll("\\r\\n", "\\n").split("\\n\\n")'
    assert correct in src
    assert broken not in src

def test_cron_schema_forbids_prompt_lane_for_predetermined_reminders():
    src = _read("honeyos/tools/cronjob_tools.py")
    assert "Predetermined-message reminders MUST use" in src
    assert "Do NOT use prompt for a predetermined-message reminder" in src
