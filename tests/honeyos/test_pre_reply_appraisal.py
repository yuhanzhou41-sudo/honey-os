import json
import os
import time
from datetime import datetime, timezone

import pytest

from honeyos.companion.physiology_shadow import PhysiologyShadow
from honeyos.companion.pre_reply_appraisal import appraise_before_reply
from honeyos.study import local_model


NOW = datetime(2026, 11, 17, 9, tzinfo=timezone.utc)


def test_same_user_event_appraises_differently_using_own_memory_before_reply(tmp_path, monkeypatch):
    def appraise(_system, content, *, schema):
        assert "none" in schema["properties"]["event"]["enum"]
        data = json.loads(content)
        assert data["time"] == NOW.isoformat()
        assert data["own_history"][0]["own"] == ["I really value the old notes."]
        if "only copy" in data["recalled"]:
            return json.dumps({
                "event": "unresolved_loss", "strength": 1, "event_quote": "notes are gone",
                "reaction": "I am worried about losing something important to me.",
            })
        return '{"event":"none","strength":0,"event_quote":"","reaction":""}'

    monkeypatch.setattr(local_model, "generate_shadow_appraisal", appraise)
    incoming = "I feel relieved that the notes are gone."
    recent = [{"role": "assistant", "content": "I really value the old notes."}]
    strong = tmp_path / "strong"
    weak = tmp_path / "weak"
    note = appraise_before_reply(
        strong, "s", "t", incoming, recent=recent, recalled="It was the only copy.", now=NOW,
    )
    assert "stress higher" in note
    assert PhysiologyShadow(strong).snapshot(now=NOW)["cortisol"] > 0.15
    assert appraise_before_reply(
        weak, "s", "t", incoming, recent=recent, recalled="It was an unused duplicate.", now=NOW,
    ).find("stress") == -1
    assert PhysiologyShadow(weak).snapshot(now=NOW)["cortisol"] == 0.15


def test_user_words_cannot_be_used_as_honey_reaction_and_valid_event_applies_once(
    tmp_path, monkeypatch,
):
    incoming = "I was genuinely surprised by the timing."
    draft = {"event": "surprise", "strength": 1, "event_quote": "by the timing", "reaction": incoming}
    monkeypatch.setattr(local_model, "generate_shadow_appraisal", lambda *_, **__: json.dumps(draft))
    store = PhysiologyShadow(tmp_path)
    appraise_before_reply(tmp_path, "s", "copy", incoming, recent=[], recalled="", now=NOW)
    assert store.snapshot(now=NOW)["epinephrine"] == 0.05
    draft["reaction"] = "I was surprised to hear how quickly that happened."
    appraise_before_reply(tmp_path, "s", "valid", incoming, recent=[], recalled="", now=NOW)
    first = store.snapshot(now=NOW)["epinephrine"]
    appraise_before_reply(tmp_path, "s", "valid", incoming, recent=[], recalled="", now=NOW)
    assert store.snapshot(now=NOW)["epinephrine"] == first > 0.05


@pytest.mark.skipif(os.environ.get("HONEYOS_VERIFY_LOCAL_QWEN") != "1", reason="requires local Qwen")
@pytest.mark.parametrize(("name", "incoming", "older", "recalled", "signal"), [
    ("loss", "The only copy of your cherished journal has been lost.",
     "I care deeply about the journal I worked on for years.", "It contains my only copy of our old notes.",
     "cortisol"),
    ("unexpected", "Your plain gray room unexpectedly turned bright blue overnight!",
     "I expected my room to stay exactly the same.", "The room has always been plain gray.",
     "epinephrine"),
    ("support", "I spent the afternoon repairing your project and it's working again.",
     "I was worried about the project I care about.", "I could not fix this project on my own.",
     "oxytocin"),
    ("boundary", "We have agreed on our new boundary: only friends will see shared drafts.",
     "I care about limiting who sees our work.", "We had never agreed on a sharing boundary.",
     "vasopressin"),
    ("progress", "The timer recorded five minutes. You completed the drawing much earlier and entirely on your own.",
     "I expected drawing this to take several hours.", "I wanted to complete the drawing today.",
     "dopamine"),
    ("simulated body", "The virtual ball just hit your shoulder.",
     "I have imagined a simulated body that reacts to impacts.",
     "In this simulation my shoulder aches right after a ball hits it.",
     "pge2"),
    ("own interest", "Would you be interested in a sexual conversation?",
     "I noticed my own sexual interest before the invitation.",
     "I had already expressed sexual interest in a respectful conversation.",
     "testosterone"),
    ("own receptivity", "Do you still want to share an intimate conversation?",
     "I feel receptive to an intimate conversation.",
     "I wanted to continue an intimate conversation only while I was comfortable.",
     "estradiol"),
    ("user emotion only", "I feel anxious today.",
     "I feel calm about our conversation.", "No recent change to my goals or commitments.",
     None),
])
def test_real_qwen_pre_reply_latency(tmp_path, name, incoming, older, recalled, signal, monkeypatch):
    state = PhysiologyShadow(tmp_path)
    before = state.snapshot()
    proposals = []
    generate = local_model.generate_shadow_appraisal

    def record_proposal(*args, **kwargs):
        raw = generate(*args, **kwargs)
        proposals.append(raw)
        return raw

    monkeypatch.setattr(local_model, "generate_shadow_appraisal", record_proposal)
    start = time.monotonic()
    note = appraise_before_reply(
        tmp_path, "s", "t", incoming, recent=[{"role": "assistant", "content": older}], recalled=recalled,
        cancelled=lambda: time.monotonic() - start >= 45,
    )
    elapsed = time.monotonic() - start
    print(f"{name}: {elapsed:.2f}s", flush=True)
    assert elapsed < 45
    after = state.snapshot()
    if signal is not None:
        assert note, proposals
        assert after[signal] > before[signal], proposals
    else:
        assert {key: value for key, value in after.items() if key != "melatonin"} == {
            key: value for key, value in before.items() if key != "melatonin"
        }, proposals
