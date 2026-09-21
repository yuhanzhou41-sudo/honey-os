from __future__ import annotations

import os
import shlex
import sys
from datetime import datetime
from pathlib import Path

from honeyos.core.constants import get_honeyos_home
from honeyos.scheduler.jobs import create_job, get_job, remove_job


class StudyPomodoroScheduler:
    """Adapter from StudySession timers to the existing HoneyOS scheduler.

    Cron only permits relative script paths inside HONEYOS_HOME/scripts.
    Phase 3 therefore creates a tiny per-session wrapper there.
    """

    @staticmethod
    def _notify() -> None:
        try:
            from honeyos.scheduler.scheduler import _notify_provider_jobs_changed
            _notify_provider_jobs_changed()
        except Exception:
            pass

    @staticmethod
    def _scripts_dir() -> Path:
        path = get_honeyos_home() / "scripts"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def _wrapper_name(cls, session_id: str) -> str:
        safe = "".join(ch for ch in session_id if ch.isalnum() or ch in {"-", "_"})
        if not safe or safe != session_id:
            raise ValueError(f"unsafe study session id: {session_id!r}")
        return f"study-pomodoro-{safe}.sh"

    @classmethod
    def _write_wrapper(cls, session_id: str) -> str:
        name = cls._wrapper_name(session_id)
        path = cls._scripts_dir() / name
        python = shlex.quote(sys.executable)
        sid = shlex.quote(session_id)
        content = (
            "#!/usr/bin/env bash\n"
            "set -u\n"
            f"{python} -m honeyos.study.pomodoro_runner complete {sid}\n"
            "status=$?\n"
            'rm -f -- "$0"\n'
            "exit $status\n"
        )
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.chmod(tmp, 0o700)
        tmp.replace(path)
        os.chmod(path, 0o700)
        return name

    @classmethod
    def _remove_wrapper_name(cls, name: str | None) -> None:
        if not name:
            return
        candidate = Path(name)
        if candidate.is_absolute() or len(candidate.parts) != 1:
            return
        if not name.startswith("study-pomodoro-") or not name.endswith(".sh"):
            return
        try:
            (cls._scripts_dir() / name).unlink()
        except FileNotFoundError:
            pass

    def schedule_completion(self, session_id: str, run_at: datetime) -> str:
        wrapper_name = self._write_wrapper(session_id)
        try:
            job = create_job(
                prompt="",
                schedule=run_at.isoformat(),
                name=f"Study Pomodoro {session_id}",
                repeat=False,
                deliver="local",
                script=wrapper_name,
                no_agent=True,
                attach_to_session=False,
            )
        except Exception:
            self._remove_wrapper_name(wrapper_name)
            raise
        self._notify()
        return str(job["id"])

    def cancel_completion(self, job_id: str | None) -> None:
        if not job_id:
            return
        job = get_job(job_id)
        wrapper_name = str(job.get("script") or "") if job else ""
        try:
            remove_job(job_id)
        finally:
            self._remove_wrapper_name(wrapper_name)
            self._notify()
