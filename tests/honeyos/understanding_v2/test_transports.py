from honeyos.agent.turn_context import compose_user_api_content, substitute_api_content
from honeyos.understanding.u2_context import wrap_understanding


def test_wire_sidecar_contains_clean_question_and_marked_context():
    context = wrap_understanding("似乎偏好先理解机制")
    sidecar = compose_user_api_content("当前问题", "", "", context)
    row = {"role": "user", "content": "当前问题", "api_content": sidecar}
    substitute_api_content(row)
    assert row["content"] == sidecar
    assert "当前问题" in row["content"] and "有限、可能不准确" in row["content"]
    assert "api_content" not in row


def test_multimodal_original_is_not_rewritten():
    original = [{"type": "text", "text": "问题"}]
    assert compose_user_api_content(original, "", "", "derived") is None
