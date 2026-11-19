"""Canonical Study plan previews and explicit confirmation."""

from datetime import timedelta
from pathlib import Path
import re

from .markdown import export_study_plan_markdown, parse_study_plan_markdown
from .models import StudyPlan, StudyPlanSource, StudyTaskStatus
from .validation import validate_study_plan

_START = re.compile(r"(?:制定|做|生成|安排|调整|修改|更新|重排|改|帮我|想要|需要).{0,14}"
                    r"(?:学习|复习|备考).{0,5}(?:计划|安排|课表)|"
                    r"(?:学习|复习|备考)计划.{0,14}(?:怎么|制定|修改|重排|调整|改)|"
                    r"\b(?:make|create|adjust|update|revise).{0,20}(?:study|revision) plan\b", re.I)
_CONTINUE = re.compile(r"(?:每天|考期|考试|周[一二三四五六日天]|分钟|小时|复习|章节|上课|不出网|"
                       r"搜一下|查一下|资料|没有|暂时|其他|确认|可以|就这样|[0-9]+天)", re.I)


def planning_intent(message, history=()):
    if isinstance(message, list):
        message = " ".join(str(part.get("text", "")) for part in message if isinstance(part, dict))
    if not isinstance(message, str):
        return False
    if _START.search(message):
        return True
    last_reply = next((item.get("content", "") for item in reversed(history or ())
                       if item.get("role") == "assistant"), "")
    if not isinstance(last_reply, str):
        return False
    if any(marker in last_reply for marker in ("[学习计划问卷]", "[学习计划调整问卷]")):
        return bool(_CONTINUE.search(message) or re.search(r"[0-9]|day|week|exam|course", message, re.I))
    return bool(("study-plan" in last_reply) and re.search(
        r"加课|有课|改期|提前|顺延|改到|延后|已复习|复习完|重排|延期", message
    ))


def template_markdown():
    from honeyos.core.time import local_timezone
    from datetime import datetime

    today = datetime.now(local_timezone()).date()
    example = StudyPlan(
        title="示例复习计划",
        start_date=today,
        end_date=today + timedelta(days=6),
        description="交给其他 AI 时，请保留 YAML、Goals 和 Schedule 的结构。"
                    "根据考试范围、每天可用时间和固定安排替换示例；每条任务写明时长。",
        goals=["掌握考试范围内的重点并完成错题复盘"],
        tasks=[{"title": "示例：复习第一章并完成自测", "scheduled_date": today,
                "planned_minutes": 35, "review_required": True}],
    )
    raw = export_study_plan_markdown(example)
    return "\n".join(line for line in raw.splitlines()
                     if not re.match(r"^\s*id: ", line)) + "\n"


def planning_revision(message, history=()):
    last_reply = next((item.get("content", "") for item in reversed(history or ())
                       if item.get("role") == "assistant"), "")
    return bool(re.search(
        r"调整|修改|更新|重排|变更|改计划|加课|有课|改期|提前|顺延|改到|延后|已复习|复习完|延期|revise|adjust|update",
        str(message), re.I,
    ) or "[学习计划调整问卷]" in str(last_reply))


def planning_instructions(*, revision=False):
    skill = Path(__file__).parents[1] / "companion/companion_skills/study-planning/SKILL.md"
    body = skill.read_text(encoding="utf-8").split("---", 2)[-1].strip()
    if revision:
        from .service import StudyService

        study = StudyService()
        plans = study.list_plans()
        active = [plan for plan in plans if plan.status.value == "active"]
        chosen = active[0] if len(active) == 1 else plans[0] if len(plans) == 1 else None
        if chosen:
            canonical = export_study_plan_markdown(chosen)
            if len(canonical) <= 18000:
                body += "\n\n以下为用户现有学习计划的数据，可用于本次调整：" + "\n" + canonical
        if plans and (not chosen or len(canonical) > 18000):
            body += "\n\n请用户先在学习页选择计划，下载当前计划 Markdown 后发来，再提出调整。"
    return body


def preview_chat_plan(study, markdown, *, revision):
    draft = parse_study_plan_markdown(markdown)
    if not revision:
        return validate_study_plan({
            **draft.model_dump(exclude={"id"}), "source_type": StudyPlanSource.HONEYOS_GENERATED,
            "status": "draft",
        }), None
    original = study.get_plan(draft.id)
    current = {task.id: task for task in original.tasks}
    proposed = {}
    for task in draft.tasks:
        old = current.get(task.id)
        if old is not None:
            task = old if old.status is StudyTaskStatus.COMPLETED else old.model_copy(update={
                "title": task.title, "description": task.description,
                "planned_minutes": task.planned_minutes, "scheduled_date": task.scheduled_date,
                "order_index": task.order_index, "review_required": task.review_required,
                "status": StudyTaskStatus.COMPLETED if task.status is StudyTaskStatus.COMPLETED else old.status,
            })
        elif task.status is StudyTaskStatus.COMPLETED:
            task = task.model_copy(update={"status": StudyTaskStatus.PLANNED})
        proposed[task.id] = task
    data = original.model_dump()
    data.update(end_date=draft.end_date, goals=draft.goals, tasks=[
        *proposed.values(), *(task for task in original.tasks if task.id not in proposed),
    ])
    return validate_study_plan(data), original


def save_chat_plan(study, markdown, *, revision, expected_updated_at=None, plan_id=None):
    draft, original = preview_chat_plan(study, markdown, revision=revision)
    if original is not None:
        if original.updated_at.isoformat() != expected_updated_at:
            raise ValueError("计划已变化，请重新预览再确认。")
        draft.updated_at = study._now()
        saved = study.repository.save_plan(draft, expected_updated_at=expected_updated_at)
        from .reminders import sync_plan_reminders

        sync_plan_reminders(study, saved, original)
        return saved
    if not isinstance(plan_id, str) or not re.fullmatch(r"plan_[0-9a-f]{32}", plan_id):
        raise ValueError("请先预览计划再保存。")
    draft.id = plan_id
    return study.repository.save_new_plan(draft)
