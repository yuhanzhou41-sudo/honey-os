from honeyos.understanding.u2_context import wrap_understanding
from honeyos.understanding.u2_runtime import sanitize_replay


def test_policy_epoch_change_removes_derived_sidecar_text():
    replay = "原用户消息\n\n" + wrap_understanding("已禁止的派生正文")
    assert "已禁止" in sanitize_replay(replay, policy_epoch_matches=True)
    cleaned = sanitize_replay(replay, policy_epoch_matches=False)
    assert cleaned == "原用户消息"


def test_multimodal_replay_is_unchanged():
    value = [{"type": "text", "text": "原消息"}]
    assert sanitize_replay(value, policy_epoch_matches=False) is value
