import sqlite3
from pathlib import Path

import pytest

from honeyos.study.markdown import (
    export_study_plan_markdown,
    parse_study_plan_markdown,
)
from honeyos.study.repository import (
    StudyPlanNotFoundError,
    StudyRepository,
)
from honeyos.study.validation import semantic_plan_dict


FIXTURES = Path(__file__).parent / "fixtures"


def fixture_plan(name: str = "medical_exam.md"):
    return parse_study_plan_markdown(
        (FIXTURES / name).read_text(encoding="utf-8")
    )


def test_repository_uses_new_study_directory(tmp_path):
    repo = StudyRepository(tmp_path)

    assert repo.db_path == tmp_path / "study" / "study.db"
    assert repo.db_path.exists()
    assert not (tmp_path / "companion" / "study.db").exists()


def test_save_and_get_plan_semantically_equal(tmp_path):
    repo = StudyRepository(tmp_path)
    original = fixture_plan()

    saved = repo.save_plan(original)
    loaded = repo.get_plan(original.id)

    assert semantic_plan_dict(saved) == semantic_plan_dict(original)
    assert semantic_plan_dict(loaded) == semantic_plan_dict(original)


def test_markdown_database_markdown_round_trip(tmp_path):
    repo = StudyRepository(tmp_path)

    first = fixture_plan()
    repo.save_plan(first)

    from_db = repo.get_plan(first.id)
    exported = export_study_plan_markdown(from_db)
    second = parse_study_plan_markdown(exported)

    assert semantic_plan_dict(second) == semantic_plan_dict(first)


def test_save_replaces_removed_tasks(tmp_path):
    repo = StudyRepository(tmp_path)
    plan = fixture_plan()

    repo.save_plan(plan)

    removed_id = plan.tasks[-1].id
    plan.tasks = plan.tasks[:-1]

    repo.save_plan(plan)
    loaded = repo.get_plan(plan.id)

    assert len(loaded.tasks) == 4
    assert removed_id not in {task.id for task in loaded.tasks}


def test_list_plans(tmp_path):
    repo = StudyRepository(tmp_path)

    first = fixture_plan("minimal.md")
    second = fixture_plan("medical_exam.md")

    repo.save_plan(first)
    repo.save_plan(second)

    ids = {plan.id for plan in repo.list_plans()}

    assert ids == {first.id, second.id}


def test_delete_plan_cascades_tasks(tmp_path):
    repo = StudyRepository(tmp_path)
    plan = fixture_plan()

    repo.save_plan(plan)
    repo.delete_plan(plan.id)

    with pytest.raises(StudyPlanNotFoundError):
        repo.get_plan(plan.id)

    with sqlite3.connect(repo.db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM study_tasks WHERE plan_id = ?",
            (plan.id,),
        ).fetchone()[0]

    assert count == 0


def test_missing_plan_raises_clear_error(tmp_path):
    repo = StudyRepository(tmp_path)

    with pytest.raises(StudyPlanNotFoundError):
        repo.get_plan("plan_does_not_exist")


def test_saving_same_plan_updates_without_duplicate_tasks(tmp_path):
    repo = StudyRepository(tmp_path)
    plan = fixture_plan("minimal.md")

    repo.save_plan(plan)

    plan.title = "Updated title"
    plan.tasks[0].title = "Updated task"

    repo.save_plan(plan)

    loaded = repo.get_plan(plan.id)

    assert loaded.title == "Updated title"
    assert len(loaded.tasks) == 1
    assert loaded.tasks[0].title == "Updated task"


def test_two_plans_can_use_same_task_title(tmp_path):
    repo = StudyRepository(tmp_path)

    first = fixture_plan("minimal.md")
    second = fixture_plan("minimal.md")

    repo.save_plan(first)
    repo.save_plan(second)

    assert len(repo.list_plans()) == 2
