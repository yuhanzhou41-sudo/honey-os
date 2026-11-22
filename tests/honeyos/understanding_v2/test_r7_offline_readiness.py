from honeyos.understanding.u2_context import compose_memory_context
from honeyos.understanding.u2_contracts import ContextSegment
from honeyos.understanding.u2_runtime import RuntimeMode, expose, sanitize_replay
from honeyos.understanding.u2_contracts import Proposal
from honeyos.understanding.u2_maintenance import apply_proposal
from honeyos.understanding.u2_manage import explain
from honeyos.understanding.u2_store import UnderstandingStore


def test_off_is_idempotent_and_budget_never_overruns():
    segments = tuple(ContextSegment(str(i), f"s:{i}", "1", "understanding", "inference",
                                    "x" * 10, 7, 9) for i in range(100))
    first = compose_memory_context(segments, total_budget=25, graph_budget=20,
                                   current_policy_epoch=9)
    second = compose_memory_context(segments, total_budget=25, graph_budget=20,
                                    current_policy_epoch=9)
    assert first == second and first.token_cost <= 20
    assert expose(RuntimeMode.OFF, context=first.text, candidate_count=100,
                  estimated_tokens=first.token_cost) == expose(
                      RuntimeMode.OFF, context="anything", candidate_count=0, estimated_tokens=0)


def test_epoch_cleanup_is_idempotent():
    clean = "原问题"
    assert sanitize_replay(clean, policy_epoch_matches=False) == clean
    assert sanitize_replay(sanitize_replay(clean, policy_epoch_matches=False),
                           policy_epoch_matches=False) == clean


def test_new_counterevidence_disputes_without_erasing_support(tmp_path):
    store = UnderstandingStore(tmp_path / "u2.db")
    store.initialize()
    first = Proposal("propose", "behavior_pattern", "work", "checks_work",
                     "似乎会反复检查", ("s1", "s2"), ())
    metadata = {
        "s1": ("g1", "session-1", "r1", "2026-11-01T00:00:00+00:00"),
        "s2": ("g2", "session-2", "r1", "2026-11-02T00:00:00+00:00"),
        "c1": ("g3", "session-3", "r2", "2026-11-03T00:00:00+00:00"),
    }
    label_id = apply_proposal(store, owner="o", lane="l", namespace="n",
                              proposal=first, evidence_meta=metadata)
    assert explain(store, label_id)["label"]["state"] == "supported"
    counter = Proposal("counter", "behavior_pattern", "work", "checks_work",
                       "近期并非总会反复检查", (), ("c1",))
    apply_proposal(store, owner="o", lane="l", namespace="n",
                   proposal=counter, evidence_meta=metadata)
    result = explain(store, label_id)
    assert result["label"]["state"] == "disputed"
    assert result["label"]["grade"] == "low"
    assert {row["relation"] for row in result["evidence"]} == {"support", "counter"}
