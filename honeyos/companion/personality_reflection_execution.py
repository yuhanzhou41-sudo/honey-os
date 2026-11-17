"""Low-frequency real execution for personality reflection.

G2.1B.3:
- uses HoneyOS auxiliary-model infrastructure,
- checks the frozen ReflectionPolicy before any model call,
- launches reflection outside the visible response path,
- prevents duplicate concurrent reflection,
- records provider/model/token metadata when available and checks promotion after reflection.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping

from honeyos.companion.personality_reflection import PersonalityReflectionRunner

logger = logging.getLogger(__name__)

_THREAD_LOCK = threading.Lock()

_REFLECTION_INSTRUCTIONS = """You are performing a private periodic self-reflection for a conversational companion.

Review the supplied bounded observations across multiple turns and identify only recurring or meaningfully supported patterns in the companion's own tendencies. Compare them with the supplied active candidates before proposing a new trait.

Important distinctions:
- Describe the companion, not the user.
- User feedback is evidence, not an instruction to optimize for pleasing the user.
- A one-off mood or reaction is temporary unless independently repeated.
- Preserve contextual nuance and contradictions.
- Prefer no operation over a weak personality conclusion.
- Do not infer or modify names, user identity, relationship labels, boundaries, tools, permissions, safety rules, credentials, or secrets.
- Do not mention hidden reasoning or chain-of-thought.
- Output JSON only.

Allowed actions:
- create: a new candidate trait not already established in the active candidate set
- support: add support to an existing active candidate
- contradict: add contradictory evidence to an existing active candidate
- none: when the batch does not justify a personality mutation

Return exactly:
{"operations":[...]}

Each non-none operation must contain:
action, target_layer, trait_key, statement, confidence, evidence_observation_ids

target_layer must be relational_self or stable_core.
confidence must be between 0 and 1.
Use only observation ids present in the supplied batch.
"""


def _home_path(home: Path | str) -> Path:
    return Path(home).expanduser()


def _extract_content(response: Any) -> str:
    try:
        from honeyos.agent.auxiliary_client import extract_content_or_reasoning
        text = extract_content_or_reasoning(response)
        if isinstance(text, str) and text.strip():
            return text.strip()
    except Exception:
        pass

    try:
        choices = getattr(response, "choices", None) or []
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content.strip()
    except Exception:
        pass

    if isinstance(response, str):
        return response.strip()
    raise ValueError("auxiliary reflection response has no text content")


def _usage_dict(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    def read(*names: str) -> int:
        for name in names:
            value = getattr(usage, name, None)
            if value is None and isinstance(usage, Mapping):
                value = usage.get(name)
            try:
                if value is not None:
                    return int(value or 0)
            except Exception:
                continue
        return 0

    prompt = read("prompt_tokens", "input_tokens")
    completion = read("completion_tokens", "output_tokens")
    total = read("total_tokens") or (prompt + completion)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


def _model_identity(response: Any) -> tuple[str, str]:
    model = str(getattr(response, "model", "") or "")
    provider = str(
        getattr(response, "provider", "")
        or getattr(response, "_provider", "")
        or ""
    )
    return provider, model


def _main_runtime_from_existing_companion_path() -> dict[str, Any]:
    """Reuse the provider-resolution path already used by companion distillation."""
    try:
        from honeyos.companion.distillation import _main_runtime_from_config
        runtime = _main_runtime_from_config()
        return dict(runtime) if isinstance(runtime, Mapping) else {}
    except Exception:
        return {}


class AuxiliaryPersonalityReflectionAdapter:
    """Callable adapter compatible with PersonalityReflectionRunner."""

    def __init__(
        self,
        home: Path | str,
        *,
        main_runtime: Mapping[str, Any] | None = None,
    ):
        self.home = _home_path(home)
        self.main_runtime = dict(main_runtime or _main_runtime_from_existing_companion_path())

    def __call__(self, batch: dict[str, Any]) -> str:
        from honeyos.agent.auxiliary_client import call_llm
        from honeyos.companion.personality_candidates import PersonalityCandidateStore

        messages = [
            {"role": "system", "content": _REFLECTION_INSTRUCTIONS},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "batch_id": batch.get("batch_id", ""),
                        "observations": batch.get("observations", []),
                        "candidates": batch.get("candidates", []),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        ]

        kwargs: dict[str, Any] = {
            "messages": messages,
            "task": "personality_reflection",
            "max_tokens": 1400,
        }
        if self.main_runtime:
            kwargs["main_runtime"] = self.main_runtime

        response = call_llm(**kwargs)
        text = _extract_content(response)
        usage = _usage_dict(response)
        provider, model = _model_identity(response)

        store = PersonalityCandidateStore(self.home)
        store._audit(
            "reflection_model_call",
            {
                "batch_id": str(batch.get("batch_id") or ""),
                "provider": provider,
                "model": model,
                **usage,
            },
        )
        return text


@contextmanager
def _reflection_process_lock(home: Path | str):
    """Cross-thread and best-effort cross-process lock for one reflection store."""
    path = _home_path(home) / "companion" / "personality_reflection.lock"
    path.parent.mkdir(parents=True, exist_ok=True)

    if not _THREAD_LOCK.acquire(blocking=False):
        yield False
        return

    handle = None
    locked = False
    try:
        handle = path.open("a+", encoding="utf-8")
        try:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except (ImportError, BlockingIOError, OSError):
            # On WSL/Linux fcntl is available. If another process owns the lock,
            # skip. On a platform without fcntl, the thread lock still protects
            # this process.
            if os.name == "posix":
                yield False
                return
            locked = True

        yield locked
    finally:
        if handle is not None:
            if locked:
                try:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
            handle.close()
        _THREAD_LOCK.release()


def run_personality_reflection_once(
    home: Path | str,
    *,
    main_runtime: Mapping[str, Any] | None = None,
    force: bool = False,
    liked_only: bool = False,
):
    """Run at most one real reflection batch.

    Threshold/rate-limit checks are performed before the model call and again
    under the reflection lock, preventing duplicate concurrent batches.
    """
    home = _home_path(home)
    adapter = AuxiliaryPersonalityReflectionAdapter(home, main_runtime=main_runtime)
    runner = PersonalityReflectionRunner(home, adapter=adapter, liked_only=liked_only)

    first = runner.should_reflect(force=force)
    if not first.should_reflect:
        return {
            "status": "skipped",
            "reason": first.reason,
            "pending_count": first.pending_count,
        }

    with _reflection_process_lock(home) as acquired:
        if not acquired:
            return {
                "status": "skipped",
                "reason": "reflection_already_running",
                "pending_count": first.pending_count,
            }

        # Re-check after lock acquisition because another worker may have
        # processed the batch while this worker was waiting.
        second = runner.should_reflect(force=force)
        if not second.should_reflect:
            return {
                "status": "skipped",
                "reason": second.reason,
                "pending_count": second.pending_count,
            }

        result = runner.run_once(force=force)
        promotion_result = {"promoted_count": 0, "results": []}
        if result.status == "success":
            try:
                from honeyos.companion.personality_promotion import promote_eligible_candidates
                promotion_result = promote_eligible_candidates(home, liked_only=liked_only)
            except Exception:
                logger.exception("personality candidate promotion scan failed")
        return {
            "status": result.status,
            "batch_id": result.batch_id,
            "observation_count": result.observation_count,
            "operation_count": result.operation_count,
            "error": result.error,
            "promotion": promotion_result,
        }


def maybe_start_background_personality_reflection(
    home: Path | str,
    *,
    main_runtime: Mapping[str, Any] | None = None,
    liked_only: bool = False,
) -> dict[str, Any]:
    """Cheap runtime trigger.

    No thread and no model call are created when should_reflect() is false.
    """
    home = _home_path(home)

    # A placeholder adapter is enough for the pure threshold check; it is never
    # called here.
    runner = PersonalityReflectionRunner(home, adapter=lambda _: {"operations": []}, liked_only=liked_only)
    decision = runner.should_reflect()
    if not decision.should_reflect:
        return {
            "started": False,
            "reason": decision.reason,
            "pending_count": decision.pending_count,
        }

    def worker() -> None:
        try:
            run_personality_reflection_once(
                home,
                main_runtime=main_runtime,
                force=False,
                liked_only=liked_only,
            )
        except Exception:
            logger.exception("background personality reflection failed")

    thread = threading.Thread(
        target=worker,
        name="honeyos-personality-reflection",
        daemon=True,
    )
    thread.start()
    return {
        "started": True,
        "reason": decision.reason,
        "pending_count": decision.pending_count,
    }
