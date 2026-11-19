"""Core study-domain models and interchange helpers for HoneyOS."""

from .models import (
    StudyPlan,
    StudyPlanSource,
    StudyPlanStatus,
    StudyResource,
    StudySession,
    StudySessionStatus,
    StudySessionType,
    StudyTask,
    StudyTaskStatus,
)
from .repository import StudyPlanNotFoundError, StudyRepository
from .validation import validate_study_plan

__all__ = [
    "StudyPlan",
    "StudyPlanSource",
    "StudyPlanStatus",
    "StudyResource",
    "StudySession",
    "StudySessionStatus",
    "StudySessionType",
    "StudyTask",
    "StudyTaskStatus",
    "StudyRepository",
    "StudyPlanNotFoundError",
    "StudyService",
    "StudyTaskNotFoundError",
    "StudySessionNotFoundError",
    "StudySessionStore",
    "StudyStorageManager",
    "StudyStorageError",
    "StudyLibraryNotFoundError",
    "TextbookService",
    "TextbookServiceError",
    "validate_study_plan",
]

from .service import StudyService, StudyTaskNotFoundError
from .session_store import StudySessionNotFoundError, StudySessionStore

# Phase 4 Study Library exports
from .library import StudyLibraryIndex, StudyLibraryIndexError
from .repository import StudyResourceNotFoundError

from .storage import StudyLibraryNotFoundError, StudyStorageError, StudyStorageManager

# Phase 6 on-demand textbook collection
from .textbook import TextbookService, TextbookServiceError
