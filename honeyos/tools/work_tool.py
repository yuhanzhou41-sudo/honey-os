"""Tools that operate on a candidate workspace while a user leads the work."""

from hashlib import sha256
import json
from pathlib import Path
import shlex
import shutil
import subprocess
from tempfile import TemporaryFile

from honeyos.companion.work_mode import active_work, save_summary, work_turn, workspace
from honeyos.tools.approval import request_single_gateway_approval
from honeyos.tools.cqmu_timetable import cqmu_date_range, read_cqmu_timetable
from honeyos.tools.registry import registry
from honeyos.utils import atomic_write_text


def _target(root: Path, path: str) -> Path:
    relative = Path(path)
    if not relative.parts or relative.is_absolute() or any(part.startswith(".") for part in relative.parts):
        raise ValueError("Use a visible relative path inside the candidate workspace.")
    result = root / relative
    if result.resolve() != result or not result.is_relative_to(root):
        raise ValueError("Symbolic links and paths outside the candidate are unavailable.")
    return result


def _run_python(root: Path, script: str) -> dict:
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise ValueError("The isolated execution backend is unavailable.")
    command = [
        bwrap, "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
        "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", "/tmp",
        "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin",
        "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--ro-bind", str(root), "/work", "--chdir", "/work",
        "/usr/bin/prlimit", "--cpu=20", "--fsize=65536", "--as=536870912", "--",
        "/usr/bin/python3", "-B", script,
    ]
    with TemporaryFile() as output:
        completed = subprocess.run(
            command, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
            timeout=25, check=False,
        )
        output.seek(0)
        return {"exit_code": completed.returncode, "output": output.read(12000).decode("utf-8", "replace")}


def work_action(args, **_):
    identity = work_turn.get()
    if not identity or identity != active_work():
        return json.dumps({"error": "Switch to work mode in the active local conversation."})
    work_id, _session_id = identity
    root = workspace(work_id).resolve()
    action = args.get("action")
    try:
        if action == "list":
            paths = sorted(str(path.relative_to(root)) for path in root.rglob("*")
                           if path.is_file() and not path.is_symlink())
            return json.dumps({"work_id": work_id, "files": paths[:100]})
        if action == "summary":
            summary = str(args.get("content") or "").strip()[:720]
            save_summary(work_id, summary)
            return json.dumps({"saved": bool(summary)})
        if action == "read_cqmu_timetable":
            start, end = cqmu_date_range(args.get("start_date"), args.get("end_date"))
            if not request_single_gateway_approval(
                "读取重庆医科大学个人课表",
                f"在本机独立 Edge 打开并单次读取个人教学日历，范围 {start} 至 {end}。只返回日期和占用课节。",
            ):
                return json.dumps({"error": "Timetable read was not approved."})
            if identity != active_work():
                raise ValueError("The active work session changed.")
            return json.dumps(read_cqmu_timetable(start, end), ensure_ascii=False)
        path = str(args.get("path") or "")
        target = _target(root, path)
        if action == "read":
            with target.open("rb") as stream:
                return json.dumps({"content": stream.read(48000).decode("utf-8"), "path": path}, ensure_ascii=False)
        if action == "write":
            content = args.get("content")
            if not isinstance(content, str) or len(content.encode()) > 48000:
                raise ValueError("Provide UTF-8 content no larger than 48 kB.")
            digest = sha256(content.encode()).hexdigest()
            description = f"写入本次候选工作区的 {path}，内容 SHA-256：{digest}。\n预览：\n{content[:600]}"
            if not request_single_gateway_approval("write candidate: " + path, description):
                return json.dumps({"error": "Write was not approved."})
            if identity != active_work():
                raise ValueError("The active work session changed.")
            target = _target(root, path)
            target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            atomic_write_text(target, content)
            return json.dumps({"written": path, "sha256": digest})
        if action == "run_python":
            if target.suffix != ".py" or not target.is_file() or target.stat().st_size > 48000:
                raise ValueError("Select one existing Python test script, no larger than 48 kB.")
            digest = sha256(target.read_bytes()).hexdigest()
            if not shutil.which("bwrap"):
                raise ValueError("The isolated execution backend is unavailable.")
            if not request_single_gateway_approval(
                "python3 -B " + shlex.quote("./" + path),
                f"在只读、断网的候选工作区运行测试。脚本 SHA-256：{digest}。",
            ):
                return json.dumps({"error": "Execution was not approved."})
            if identity != active_work() or sha256(_target(root, path).read_bytes()).hexdigest() != digest:
                raise ValueError("The active work session or approved script changed.")
            return json.dumps(_run_python(root, "./" + path), ensure_ascii=False)
        raise ValueError("Unknown work action.")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        return json.dumps({"error": str(error)}, ensure_ascii=False)


registry.register(
    name="work_action",
    toolset="companion_work",
    schema={
        "name": "work_action",
        "description": "Inspect or create candidate skill and feature files, test a Python script in an offline sandbox, or record a completion summary. Can also read occupied periods from the CQMU personal timetable using the local Edge session. Writes, execution and timetable reading require separate user approval.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "read", "write", "run_python", "summary", "read_cqmu_timetable"]},
                "path": {"type": "string", "description": "Visible relative candidate file path."},
                "content": {"type": "string", "description": "Complete file text or final work summary."},
                "start_date": {"type": "string", "description": "Inclusive CQMU timetable start date, YYYY-MM-DD."},
                "end_date": {"type": "string", "description": "Inclusive CQMU timetable end date, YYYY-MM-DD."},
            },
            "required": ["action"],
        },
    },
    handler=work_action,
)
