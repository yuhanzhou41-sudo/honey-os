import base64
import json

import pytest

from honeyos.study.repository import StudyRepository
from honeyos.study import question_intake
from honeyos.study.review import StudyReview
from honeyos.study.review_http import _answer, _card_preview, _extract_question, _question_preview, _upload_drafts, _web_drafts
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


def test_daily_recall_scopes_cards_and_records_mastery(review):
    store, source = review
    question_id = question(store, source)
    store.attempt(question_id, 1, "wrong")
    store.save_cards(None, question_id, [{"front": "Recall the carrier", "back": "ATP", "excerpt": QUOTE}])
    assert store.draw_card({"keyword": "chemistry"}) == {"card": None, "matched": 0}
    scope = {"keyword": "atp", "wrong": True, "resource_id": source}
    card = store.draw_card(scope)["card"]
    assert set(card) == {"front", "id"}
    payload = {"id": "recall", "response": "ATP"}
    first = store.recall(card["id"], payload)
    assert first["card"]["excerpt"] == QUOTE
    assert store.recall(card["id"], payload) == first
    assert first["recall"]["rating"] is None
    rating = store.assess("recall", 2)
    assert store.assess("recall", 2) == rating
    assert StudyReview(store.study).recall_history()[0]["rating"] == 2
    assert store.draw_card(scope) == {"card": None, "matched": 1}


def test_daily_quiz_is_atomic_and_results_update_wrong_items(review):
    store, source = review
    scope = {"keyword": "energy", "count": 10}
    assert store.create_quiz(scope)["available"] == 0
    for _ in range(10):
        question(store, source)
    quiz = store.create_quiz(scope)
    assert all("correct" not in item and "excerpt" not in item for item in quiz["questions"])
    with pytest.raises(ValueError):
        store.submit_quiz(quiz["id"], [1] + [0] * 8 + [9])
    first_id = quiz["questions"][0]["id"]
    assert store.history(first_id)["attempts"] == []
    choices = [1] + [0] * 9
    graded = store.submit_quiz(quiz["id"], choices)
    assert graded["score"] == 9
    assert graded["results"][0]["question"]["excerpt"] == QUOTE
    assert store.submit_quiz(quiz["id"], choices) == graded
    with pytest.raises(ValueError):
        store.submit_quiz(quiz["id"], [0] * 10)
    assert len(store.history(first_id)["attempts"]) == 1
    assert [item["id"] for item in store.list_questions(wrong_only=True)] == [first_id]
    summary = store.daily_summary("Asia/Shanghai")
    assert (summary["attempts"], summary["correct"]) == (10, 9)


def test_past_import_checks_source_and_reports_available_count(review):
    store, _ = review
    original = "2025 Science Exam. Carrier? A. ATP B. DNA"
    attachment = store.study.attachments.upload_bytes(original.encode(), original_filename="exam.txt")
    source = store.study.create_resource({"attachment_id": attachment.id, "title": "2025 Science Exam"})
    item = {"prompt": "Carrier?", "options": ["ATP", "DNA"], "correct": 0, "excerpt": original,
            "exam": "Science Exam", "year": 2025, "location": "Q1"}
    payload = {"kind": "past", "resource_id": source.id}
    with pytest.raises(ValueError):
        store.import_questions({**payload, "questions": [item, {**item, "year": 2024}]})
    assert not store.list_questions()
    assert store.import_questions({**payload, "questions": [item]}) == {"imported": 1}
    with pytest.raises(ValueError):
        store.import_questions({**payload, "questions": [item]})
    assert store.create_quiz({"kind": "past", "keyword": "carrier", "count": 10})["available"] == 1
    assert store.list_questions()[0]["location"] == "Q1"


def test_local_question_drafts_check_the_selected_segment(monkeypatch, review):
    store, source = review
    candidate = {"prompt": "Carrier?", "options": ["ATP", "DNA"], "correct": 0, "evidence_id": 1}
    monkeypatch.setattr("honeyos.study.review_http.generate_question_candidates",
                        lambda *args: json.dumps({"questions": [candidate]}))
    expected = {key: value for key, value in candidate.items() if key != "evidence_id"}
    assert _question_preview(store, {"resource_id": source})["questions"] == [{**expected, "excerpt": QUOTE}]
    assert not store.list_questions()
    with pytest.raises(ValueError):
        _question_preview(store, {"resource_id": source, "segment": 2})
    candidate["evidence_id"] = 99
    with pytest.raises(ValueError):
        _question_preview(store, {"resource_id": source})


def test_flashcard_preview_does_not_save_and_checks_quoted_source(monkeypatch, review):
    store, source = review
    question_id = question(store, source)
    with pytest.raises(ValueError):
        store.card_context(None, question_id)
    store.attempt(question_id, 1, "wrong")
    card = {"front": "What carries energy?", "back": "ATP", "excerpt": QUOTE}
    monkeypatch.setattr("honeyos.study.review_http.generate_flashcard_candidates",
                        lambda *a: json.dumps({"cards": [card]}))
    monkeypatch.setattr("honeyos.study.review_http._study_reply",
                        lambda *a, **kw: pytest.fail("Flashcards must not use the main model"))
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


def test_uploaded_drafts_require_review_and_do_not_store_generated_answers(monkeypatch, review):
    store, _ = review
    original = "Which is the carrier? A. ATP B. DNA"
    item = {"prompt": "Which is the carrier?", "options": ["ATP", "DNA"], "correct": None, "excerpt": original}
    monkeypatch.setattr(question_intake, "generate_question_candidates", lambda *args: json.dumps({"questions": [item]}))
    draft = _upload_drafts(store, {"filename": "quiz.txt", "data": base64.b64encode(original.encode()).decode()})
    assert draft["questions"] == [{**item, "explanation": ""}]
    assert not store.list_questions()
    payload = {"source_id": draft["source"]["id"], "questions": draft["questions"]}
    with pytest.raises(ValueError):
        store.save_intake(payload)
    payload["questions"][0]["correct"] = 0
    assert store.save_intake(payload) == store.save_intake(payload) == {"imported": 1}
    row = store.list_questions()[0]
    assert row["kind"] == "upload"
    assert store.attempt(row["id"], 0, "upload-attempt")["attempt"]["correct"]


def test_web_import_preserves_url_and_checks_claimed_exam(monkeypatch, review):
    from honeyos.tools import web_tools

    store, _ = review
    url = "https://exams.example.org/science/2025"
    original = "2025 Science Exam. Carrier? A. ATP B. DNA"
    monkeypatch.setattr(web_tools, "web_search_tool", lambda query, limit: json.dumps({"success": True, "data": {"web": [
        {"url": url, "title": "2025 Science Exam"}, {"url": "javascript:alert(1)"}, {"url": "http://127.0.0.1/admin"},
    ]}}))

    async def extract(urls, **options):
        assert urls == [url]
        return json.dumps({"results": [{"title": "2025 Science Exam", "content": original}]})

    monkeypatch.setattr(web_tools, "web_extract_tool", extract)
    item = {"prompt": "Carrier?", "options": ["ATP", "DNA"], "correct": 0, "excerpt": original}
    monkeypatch.setattr(question_intake, "generate_question_candidates", lambda *args: json.dumps({"questions": [item]}))
    assert [source["url"] for source in question_intake.search_past_questions({"topic": "Science"})["sources"]] == [url]
    draft = _web_drafts(store, {"url": url})
    source_id = draft["source"]["id"]
    claimed = {**draft["questions"][0], "verified_past": True, "exam": "Science Exam", "year": 2024, "location": "Q1"}
    with pytest.raises(ValueError):
        store.save_intake({"source_id": source_id, "questions": [claimed]})
    assert not store.list_questions()
    claimed["year"] = 2025
    store.save_intake({"source_id": source_id, "questions": [claimed]})
    question = store.list_questions()[0]
    assert question["kind"] == "past"
    assert question["source_url"] == url and store.history(question["id"])["question"]["source_url"] == url


def test_practice_generation_requires_consent_and_reads_selected_plan(monkeypatch, review):
    store, _ = review
    plan = store.study.create_plan({
        "title": "Cell biology", "start_date": "2026-11-17", "end_date": "2026-11-17",
    })
    plan = store.study.create_task(plan.id, {"title": "ATP and energy", "scheduled_date": "2026-11-17"})
    requested = {"topic": "Biology", "plan_id": plan.id, "task_ids": [plan.tasks[0].id]}
    calls = []

    def model(system, payload):
        calls.append(json.loads(payload)["review_scope"])
        return json.dumps({"questions": [{"prompt": "What is the carrier?", "options": ["ATP", "DNA"], "correct": 0}]})

    monkeypatch.setattr(question_intake, "generate_question_candidates", model)
    with pytest.raises(ValueError):
        question_intake.practice_drafts(store, requested)
    assert not calls
    draft = question_intake.practice_drafts(store, {**requested, "consent": True})
    assert len(calls) == 1 and "ATP and energy" in calls[0]
    store.save_intake({"source_id": draft["source"]["id"], "questions": draft["questions"]})
    assert store.list_questions()[0]["kind"] == "mock"
