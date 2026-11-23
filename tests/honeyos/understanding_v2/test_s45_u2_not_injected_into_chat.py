"""S4.5 verification: U2 labels do NOT reach the chat prompt (fail-closed).

Task 2 requires proving the *actual* read path from the U2 store into chat
context — not just that labels are generated and graphed. The production chat
context is assembled in ``honeyos.agent.turn_context.build_turn_context``, which
calls ``StructuredMemoryStore.context_for_lane``. This test asserts that even
when a valid, supported U2 label exists in the store, its body never appears in
the assembled lane context, and that the runtime ``expose`` gate stays
fail-closed without an authorized switch.

This is an intentional safety boundary, NOT a defect being "fixed": enabling
injection requires the recall-pipeline wiring recorded as deferred in the S4
scope doc and an explicit authorization decision. This test locks the current
fail-closed contract so it cannot silently change.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from honeyos.companion.continuity import StructuredMemoryStore
from honeyos.understanding.u2_contracts import ContextSegment, Proposal
from honeyos.understanding.u2_context import compose_memory_context
from honeyos.understanding.u2_maintenance import apply_proposal
from honeyos.understanding.u2_runtime import RuntimeMode, expose
from honeyos.understanding.u2_store import UnderstandingStore

OWNER, LANE, NS = "local-owner", "lane", "general"
SENTINEL = "ZZZ_U2_SENTINEL_BODY_9QK2"


def _seed(tmp_path: Path) -> None:
    """One active continuity episode + one supported U2 label citing it."""
    c_store = StructuredMemoryStore(tmp_path)
    item = c_store.record(
        lane_key=LANE, kind="episode",
        content="用户说过他更喜欢先弄懂机制再背结论 mechanism first",
        evidence="user_stated", source_session_id="s1", importance="high",
        created_by="background", now=datetime.now(timezone.utc),
    )
    assert item is not None
    ref = f"continuity:{item.id}"
    store = UnderstandingStore(tmp_path / "understanding_v2.db")
    store.initialize()
    apply_proposal(
        store, owner=OWNER, lane=LANE, namespace=NS,
        proposal=Proposal("propose", "interest_preference", "learning",
                          "mechanism_first", SENTINEL, (ref,), ()),
        evidence_meta={ref: ("g1", "s1", "rev",
                             datetime.now(timezone.utc).isoformat())},
        continuity_db_path=tmp_path / "continuity.db",
    )


def test_lane_context_excludes_u2_label_body(tmp_path):
    _seed(tmp_path)
    ctx = StructuredMemoryStore(tmp_path).context_for_lane(
        lane_key=LANE, query="mechanism")
    # The continuity memory is relevant and returned...
    assert ctx is not None and "先弄懂机制" in ctx
    # ...but the U2 label's derived body never reaches the prompt.
    assert SENTINEL not in ctx


def test_expose_gate_stays_fail_closed_without_authorization():
    segments = (ContextSegment("u", "label", "1", "understanding", "inference",
                               SENTINEL, 8, 2),)
    composed = compose_memory_context(segments, total_budget=80, graph_budget=40,
                                      current_policy_epoch=2)

    off = expose(RuntimeMode.OFF, context=composed.text, candidate_count=1,
                 estimated_tokens=8)
    assert off.context == "" and off.injected is False and off.candidate_count == 0

    shadow = expose(RuntimeMode.SHADOW, context=composed.text, candidate_count=1,
                    estimated_tokens=8)
    assert shadow.injected is False and shadow.context == ""

    with pytest.raises(PermissionError):
        expose(RuntimeMode.ACTIVE, context=composed.text, candidate_count=1,
               estimated_tokens=8)
    # Explicit authorization is the only path that injects, and even then only
    # the already-budgeted + epoch-checked text is passed through.
    active = expose(RuntimeMode.ACTIVE, context=composed.text, candidate_count=1,
                    estimated_tokens=8, active_authorized=True)
    assert active.injected is True and SENTINEL in active.context
