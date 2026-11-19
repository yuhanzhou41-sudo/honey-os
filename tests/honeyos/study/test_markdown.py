from pathlib import Path

import pytest

from honeyos.study.markdown import (
    StudyPlanMarkdownError,
    export_study_plan_markdown,
    parse_study_plan_markdown,
)
from honeyos.study.validation import semantic_plan_dict


FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_minimal_markdown_import():
    plan = parse_study_plan_markdown(read_fixture("minimal.md"))

    assert plan.title == "Minimal Study Plan"
    assert len(plan.goals) == 1
    assert len(plan.tasks) == 1
    assert plan.tasks[0].title == "阅读第一章"
    assert plan.tasks[0].planned_minutes == 40


def test_medical_exam_markdown_import():
    plan = parse_study_plan_markdown(read_fixture("medical_exam.md"))

    assert plan.title == "血液及免疫系统期末复习"
    assert len(plan.goals) == 3
    assert len(plan.tasks) == 5
    assert sum(task.review_required for task in plan.tasks) == 4


def test_invalid_plan_is_rejected():
    with pytest.raises(StudyPlanMarkdownError):
        parse_study_plan_markdown(read_fixture("invalid.md"))


def test_markdown_semantic_round_trip():
    first = parse_study_plan_markdown(read_fixture("medical_exam.md"))

    exported = export_study_plan_markdown(first)

    second = parse_study_plan_markdown(exported)

    assert semantic_plan_dict(second) == semantic_plan_dict(first)


def test_export_contains_version_marker():
    plan = parse_study_plan_markdown(read_fixture("minimal.md"))

    exported = export_study_plan_markdown(plan)

    assert "study_plan_version: 1" in exported
    assert "# Schedule" in exported


def test_missing_frontmatter_is_rejected():
    with pytest.raises(StudyPlanMarkdownError):
        parse_study_plan_markdown(
            "# Goals\n- test\n\n# Schedule\n"
        )


def test_unsupported_task_metadata_is_rejected():
    text = """---
study_plan_version: 1
title: Invalid Metadata
start_date: 2026-09-21
end_date: 2026-09-21
---

# Schedule

## 2026-09-21

- [ ] Task
  unknown_field: value
"""

    with pytest.raises(StudyPlanMarkdownError):
        parse_study_plan_markdown(text)


def test_task_before_schedule_date_is_rejected():
    text = """---
study_plan_version: 1
title: Missing Date
start_date: 2026-09-21
end_date: 2026-09-21
---

# Schedule

- [ ] Task
  duration: 40
"""

    with pytest.raises(StudyPlanMarkdownError):
        parse_study_plan_markdown(text)


@pytest.mark.parametrize("field", ["minimum_required", "sunlight", "unexpected"])
def test_unknown_frontmatter_is_rejected(field):
    markdown = read_fixture("minimal.md").replace(
        "study_plan_version: 1", f"study_plan_version: 1\n{field}: true"
    )
    with pytest.raises(StudyPlanMarkdownError, match="unsupported front matter"):
        parse_study_plan_markdown(markdown)
