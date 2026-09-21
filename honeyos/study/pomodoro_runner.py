from __future__ import annotations

import sys

from honeyos.core.constants import get_honeyos_home

from .repository import StudyRepository
from .service import StudyService
from .session_store import StudySessionNotFoundError


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] != "complete":
        return 2

    # Cron is HONEYOS_HOME/profile scoped, so resolve Study persistence from
    # that same home for scheduled completion.
    service = StudyService(StudyRepository(get_honeyos_home()))

    try:
        service.complete_session(args[1], scheduled=True)
    except StudySessionNotFoundError:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
