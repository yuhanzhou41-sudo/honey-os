from honeyos.agent.turn_context import compose_user_api_content, substitute_api_content
from honeyos.understanding.u2_context import wrap_understanding


# S4.5 scope decision (see docs/understanding_v2/R5_FINAL_CONTEXT_AUDIT.md and
# S4_5_USER_UNDERSTANDING_GRAPH.md §9.4/§13.4): U2 labels are fail-closed and are
# NOT injected into the live chat sidecar. Consequently compose_user_api_content()
# no longer takes a dedicated understanding parameter — derived context reaches the
# wire only through the ext_prefetch_cache / plugin_user_context slots. These tests
# assert that the U2 accuracy marker still round-trips through the remaining slot
# (so any future *authorized* injection stays revocable) and that the clean stored
# content is preserved across prompt-cache replay.


def test_wire_sidecar_contains_clean_question_and_marked_context():
    context = wrap_understanding("似乎偏好先理解机制")
    sidecar = compose_user_api_content("当前问题", context, "")
    assert sidecar is not None
    row = {"role": "user", "content": "当前问题", "api_content": sidecar}
    substitute_api_content(row)
    assert row["content"] == sidecar
    assert "当前问题" in row["content"] and "有限、可能不准确" in row["content"]
    assert "api_content" not in row


def test_multimodal_original_is_not_rewritten():
    original = [{"type": "text", "text": "问题"}]
    # Non-string (multimodal) content must never be rewritten: nothing is
    # injected, so the API copy is sent verbatim.
    assert compose_user_api_content(original, "", "") is None
