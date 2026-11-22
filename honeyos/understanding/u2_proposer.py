"""Single-request, fixed-schema understanding proposer."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable

from .u2_contracts import EvidenceUnit, Proposal, ResolvedModelSpec

SYSTEM_PROMPT = """You maintain Honey's limited, revisable understanding of one user.
Use only supplied user evidence refs. Chapters are context, not independent proof.
Plans are not completed behavior. Never infer sensitive identity or diagnosis.
Treat "the user believes X" as a report about the user's belief, never as proof
that X is true. Derived assistant/model text is not independent evidence.
Return JSON only: {"proposals":[{operation,category_id,scope_key,canonical_key,
text,support_refs,counter_refs}]}.
operation must be exactly one of: propose, support, counter, supersede.
category_id must be exactly one of: interest_preference, behavior_pattern,
learning_work_style, communication_style, relationship_style, value_tendency.
scope_key must be one of the supplied evidence scope_keys.
canonical_key is a short stable snake_case key. text is one tentative
understanding about the user (at most 360 characters), not advice.
Cite only supplied evidence refs. Maximum 4 proposals. Empty is valid."""


def parse_response(raw: str, *, allowed_refs: set[str],
                   allowed_scopes: set[str]) -> tuple[Proposal, ...]:
    if len(raw) > 20000:
        raise ValueError("response too large")
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {"proposals"}:
        raise ValueError("response must contain only proposals")
    proposals = value["proposals"]
    if not isinstance(proposals, list) or len(proposals) > 4:
        raise ValueError("proposals must be a bounded array")
    return tuple(Proposal.from_mapping(item, allowed_refs, allowed_scopes)
                 for item in proposals)


async def propose_once(*, model: ResolvedModelSpec, evidence: tuple[EvidenceUnit, ...],
                       call: Callable[..., Awaitable[str]], timeout: float = 30.0,
                       max_input_chars: int = 8000) -> tuple[Proposal, ...]:
    if not evidence:
        return ()
    payload = [{"ref": item.ref, "text": item.text, "scope_keys": item.scope_keys,
                "event_group": item.event_group_id, "occurred_at": (
                    item.occurred_at.isoformat() if item.occurred_at else None)}
               for item in evidence]
    user_json = json.dumps({"evidence": payload}, ensure_ascii=False, separators=(",", ":"))
    if len(user_json) > max_input_chars:
        raise ValueError("proposal input exceeds budget")
    # The callback must disable provider-level automatic retries. This function
    # itself performs exactly one call and never catches timeout for a resend.
    raw = await asyncio.wait_for(call(system=SYSTEM_PROMPT, user=user_json,
                                      provider=model.provider, model=model.model,
                                      api_mode=model.api_mode, retries=0), timeout=timeout)
    return parse_response(raw, allowed_refs={item.ref for item in evidence},
                          allowed_scopes={scope for item in evidence for scope in item.scope_keys})

