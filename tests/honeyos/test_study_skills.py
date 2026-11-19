import json

import pytest

from honeyos.companion import study_skills


def test_registry_review_run_disable_and_rollback(monkeypatch, tmp_path):
    monkeypatch.setenv("HONEYOS_HOME", str(tmp_path))
    first = json.dumps({"name": "Review", "purpose": "Format study notes", "heading": "First"})
    second = json.dumps({"name": "Review", "purpose": "Format study notes", "heading": "Second"})
    with pytest.raises(ValueError):
        study_skills.submit('{"script":"external.py"}', "test-work")
    assert study_skills.status()["candidates"] == []
    assert study_skills.submit(first, "test-work") == 1
    assert study_skills.submit(first, "test-work") == 1
    assert study_skills.submit(second, "test-work") == 2
    new, old = study_skills.status()["candidates"]
    with pytest.raises(ValueError):
        study_skills.run("test")
    with pytest.raises(ValueError):
        study_skills.change("enable", 1, new["digest"])
    with pytest.raises(ValueError):
        study_skills.change("rollback", 1, old["digest"])
    study_skills.change("enable", 1, old["digest"])
    assert study_skills.run("x\n\ny") == "First\n\n• x\n• y"
    study_skills.change("enable", 2, new["digest"])
    assert study_skills.run("x").startswith("Second")
    study_skills.change("rollback", 1, old["digest"])
    assert study_skills.run("x").startswith("First")
    study_skills.change("disable", 1, old["digest"])
    with pytest.raises(ValueError):
        study_skills.run("test")
