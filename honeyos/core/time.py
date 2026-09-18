"""
Timezone-aware clock for HoneyOS.

Provides a single ``now()`` helper that returns a timezone-aware datetime
based on the user's configured IANA timezone (e.g. ``Asia/Kolkata``).

Resolution order:
  1. ``HONEYOS_TIMEZONE`` environment variable
  2. ``timezone`` key in ``~/.honeyos/config.yaml``
  3. Falls back to the server's local time (``datetime.now().astimezone()``)

Invalid timezone values log a warning and fall back safely — HoneyOS never
crashes due to a bad timezone string.
"""

import logging
import os
from datetime import date, datetime, timezone, tzinfo
from honeyos.core.constants import get_config_path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Python 3.8 fallback (shouldn't be needed — HoneyOS requires 3.9+)
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

# Cached state — resolved once, reused on every call.
# Call reset_cache() to force re-resolution (e.g. after config changes).
_cached_tz: Optional[ZoneInfo] = None
_cached_tz_name: Optional[str] = None
_cache_resolved: bool = False


def _resolve_timezone_name() -> str:
    """Read the configured IANA timezone string (or empty string).

    This does file I/O when falling through to config.yaml, so callers
    should cache the result rather than calling on every ``now()``.
    """
    # 1. Environment variable (highest priority — set by Supervisor, etc.)
    tz_env = os.getenv("HONEYOS_TIMEZONE", "").strip()
    if tz_env:
        return tz_env

    # 2. config.yaml ``timezone`` key
    try:
        # Prefer the shared cached raw-config reader (mtime/size-keyed cache +
        # libyaml C loader) — a direct yaml.safe_load of a large config.yaml
        # costs ~100ms+ and this used to run inside the FIRST system prompt
        # build, on the time-to-first-token critical path.
        try:
            from honeyos.runtime.config import read_raw_config
            cfg = read_raw_config() or {}
        except Exception:
            import yaml
            config_path = get_config_path()
            if config_path.exists():
                with open(config_path, encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
            else:
                cfg = {}
        if cfg:
            # Managed scope: an administrator can pin ``timezone`` too. Overlay
            # via the shared helper (fail-open) since this reads config.yaml directly.
            try:
                from honeyos.runtime import managed_scope
                cfg = managed_scope.apply_managed_overlay(cfg)
            except Exception:
                pass
            tz_cfg = cfg.get("timezone", "")
            if isinstance(tz_cfg, str) and tz_cfg.strip():
                return tz_cfg.strip()
    except Exception:
        pass

    return ""


def _get_zoneinfo(name: str) -> Optional[ZoneInfo]:
    """Validate and return a ZoneInfo, or None if invalid."""
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (KeyError, Exception) as exc:
        logger.warning(
            "Invalid timezone '%s': %s. Falling back to server local time.",
            name, exc,
        )
        return None


def get_timezone() -> Optional[ZoneInfo]:
    """Return the user's configured ZoneInfo, or None (meaning server-local).

    Resolved once and cached. Call ``reset_cache()`` after config changes.
    """
    global _cached_tz, _cached_tz_name, _cache_resolved
    if not _cache_resolved:
        _cached_tz_name = _resolve_timezone_name()
        _cached_tz = _get_zoneinfo(_cached_tz_name)
        _cache_resolved = True
    return _cached_tz


def reset_cache() -> None:
    """Clear the cached timezone so the next call re-resolves it.

    Call this after the configured timezone may have changed (e.g. after a
    config edit or ``HONEYOS_TIMEZONE`` update) to force ``get_timezone()`` /
    ``now()`` to read the new value instead of the value cached at first use.
    """
    global _cached_tz, _cached_tz_name, _cache_resolved
    _cached_tz = None
    _cached_tz_name = None
    _cache_resolved = False


def now() -> datetime:
    """
    Return the current time as a timezone-aware datetime.

    If a valid timezone is configured, returns wall-clock time in that zone.
    Otherwise returns the server's local time (via ``astimezone()``).
    """
    return datetime.now(local_timezone())


def local_timezone() -> tzinfo:
    """Return the effective HoneyOS local timezone, never ``None``.

    ``get_timezone()`` remains the compatibility API that reports only an
    explicitly configured IANA zone.  User-facing calendar semantics should
    use this function so every caller shares the same configured-or-host-local
    fallback.
    """
    configured = get_timezone()
    if configured is not None:
        return configured
    return datetime.now().astimezone().tzinfo or timezone.utc


def utc_now() -> datetime:
    """Return the current storage/expiry clock in UTC."""
    return datetime.now(timezone.utc)


def to_local(value: datetime) -> datetime:
    """Convert an aware datetime to the effective HoneyOS local timezone.

    Naive values are interpreted as local wall-clock values.  Callers parsing
    untrusted or historical timestamps should reject naive values before using
    this helper when guessing a zone would be unsafe.
    """
    zone = local_timezone()
    if value.tzinfo is None:
        return value.replace(tzinfo=zone)
    return value.astimezone(zone)


def local_date(value: datetime | None = None) -> date:
    """Return the HoneyOS-local calendar date for ``value`` or the live clock."""
    return (to_local(value) if value is not None else now()).date()


def timezone_name(value: datetime | None = None) -> str:
    """Return a stable display name for the effective local timezone."""
    zone = local_timezone()
    key = getattr(zone, "key", None)
    if isinstance(key, str) and key:
        return key
    current = to_local(value) if value is not None else now()
    return current.tzname() or str(zone) or "local"


def format_runtime_time_context(current: datetime | None = None) -> str:
    """Render the authoritative local clock snapshot for one model run.

    System prompts are cached for long-lived sessions, so their session-start
    date is historical metadata rather than a live clock.  This block is
    intentionally suitable for per-turn user-message sidecar injection and
    auxiliary companion calls.
    """
    current = to_local(current) if current is not None else now()
    offset = current.strftime("%z")
    offset_text = (
        f"UTC{offset[:3]}:{offset[3:]}"
        if len(offset) == 5
        else "UTC offset unavailable"
    )
    return (
        "[Runtime time context]\n"
        f"Current local datetime: {current.isoformat(timespec='seconds')}\n"
        f"Current local date: {current.date().isoformat()}\n"
        f"Timezone: {timezone_name(current)} ({offset_text})\n"
        "This is the authoritative 'now' for this run. Resolve diary dates, "
        "reminders, schedules, and relative expressions such as today/今天, "
        "tonight/今晚, and tomorrow/明天 from this value. Conversation/session "
        "start timestamps are historical metadata and must never replace it."
    )
