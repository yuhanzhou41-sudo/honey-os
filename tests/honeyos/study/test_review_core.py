import base64
import json

import pytest

from honeyos.study.repository import StudyRepository
from honeyos.study.review import StudyReview
from honeyos.study.review_http import _answer, _card_preview, _extract_question
from honeyos.study.service import StudyService

QUOTE = "ATP is a common cellular energy carrier."


@pytest.fixture
def review(tmp_path):
    study = StudyService(StudyRepository(tmp_path))
    attachment = study.attachments.upload_bytes(QUOTE.encode(), original_filename="biology.txt")
    resource = study.create_resource({"attachment_id": attachment.id, "title": "Biology"})
    return StudyReview(study), resource.id


def question(store, resource_id):
    return store.create_question({
        "prompt": "Which molecule carries energy?",
        "options": ["ATP", "DNA"], "correct": 0,
        "resource_id": resource_id, "excerpt": QUOTE,
    })


def test_retry_records_each_attempt_once_and_keeps_history(review):
    store, source = review
    question_id = question(store, source)
    assert "correct" not in store.list_questions()[0]
    first = store.attempt(question_id, 1, "first")
    assert not first["attempt"]["correct"]
    assert store.attempt(question_id, 1, "first") == first
    with pytest.raises(ValueError):
        store.attempt(question_id, 0, "first")
    assert store.list_questions(wrong_only=True)[0]["id"] == question_id
    assert store.attempt(question_id, 0, "second")["attempt"]["correct"]
    reopened = StudyReview(store.study)
    assert not reopened.list_questions(wrong_only=True)
    assert [a["choice"] for a in reopened.history(question_id)["attempts"]] == [0, 1]


def test_flashcard_preview_does_not_save_and_checks_quoted_source(monkeypatch, review):
    store, source = review
    question_id = question(store, source)
    with pytest.raises(ValueError):
        store.card_context(None, question_id)
    store.attempt(question_id, 1, "wrong")
    card = {"front": "What carries energy?", "back": "ATP", "excerpt": QUOTE}
    monkeypatch.setattr("honeyos.study.review_http._study_reply", lambda *a, **kw: json.dumps({"cards": [card]}))
    preview = _card_preview(store, {"question_id": question_id})
    assert preview["question_id"] == question_id and not store.list_cards()
    with pytest.raises(ValueError):
        store.save_cards(None, question_id, [{**card, "excerpt": "invented source"}])
    assert not store.list_cards()
    store.save_cards(None, question_id, [{**card, "back": "Edited ATP"}])
    assert store.list_cards()[0]["back"] == "Edited ATP"
    assert store.list_cards()[0]["resource_id"] == source


def test_uploaded_question_rejects_missing_content_and_false_citation(monkeypatch, review):
    store, source = review
    uploaded = _extract_question({"filename": "question.txt", "data": base64.b64encode(b"What is ATP?").decode()})
    assert uploaded["question"] == "What is ATP?"
    with pytest.raises(ValueError):
        _answer(store, {"question": "The chart reads [无法识别]", "resource_id": source})
    monkeypatch.setattr("honeyos.study.review_http._study_reply",
                        lambda *a, **kw: json.dumps({"answer": "ATP", "quotes": ["invented source"]}))
    with pytest.raises(ValueError):
        _answer(store, {"question": uploaded["question"], "resource_id": source})
    monkeypatch.setattr("honeyos.study.review_http._study_reply",
                        lambda *a, **kw: json.dumps({"answer": "ATP", "quotes": [QUOTE]}))
    assert _answer(store, {"question": uploaded["question"], "resource_id": source})["citations"][0]["excerpt"] == QUOTE


def test_image_extraction_uses_vision_and_preserves_uncertainty(monkeypatch):
    def vision(system, content, *, vision):
        assert vision
        assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
        return "Read the chart: [无法识别]"
    monkeypatch.setattr("honeyos.study.review_http._study_reply", vision)
    encoded = base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode()
    assert "[无法识别]" in _extract_question({"filename": "photo.png", "data": encoded})["question"]
