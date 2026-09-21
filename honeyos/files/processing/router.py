from __future__ import annotations

from honeyos.files.processing.models import (
    ProcessingCapability,
    ProcessingRequest,
    ProcessingResult,
    ProcessingStatus,
    VisualCoverage,
)
from honeyos.files.processing.registry import ProviderRegistry


class TaskRouter:
    """Minimal deterministic router for HoneyOS file processing.

    Phase 1 intentionally contains no learned routing policy.
    It only selects providers by required capability and fails explicitly
    when a required capability is unavailable.
    """

    def __init__(self, registry: ProviderRegistry):
        self.registry = registry

    def route_text(
        self,
        request: ProcessingRequest,
    ) -> ProcessingResult:
        providers = self.registry.providers_for(
            ProcessingCapability.TEXT
        )

        if not providers:
            return ProcessingResult(
                status=ProcessingStatus.UNAVAILABLE,
                provider_id="none",
                capability=ProcessingCapability.TEXT,
                output={},
                visual_coverage=VisualCoverage.NOT_APPLICABLE,
                warnings=[
                    "No text model provider is configured."
                ],
            )

        return providers[0].process(request)

    def route_vision(
        self,
        request: ProcessingRequest,
    ) -> ProcessingResult:
        if not request.image_refs:
            return ProcessingResult(
                status=ProcessingStatus.COMPLETE,
                provider_id="none",
                capability=ProcessingCapability.VISION,
                output={},
                visual_coverage=VisualCoverage.NOT_APPLICABLE,
            )

        providers = self.registry.providers_for(
            ProcessingCapability.VISION
        )

        if not providers:
            return ProcessingResult(
                status=ProcessingStatus.UNAVAILABLE,
                provider_id="none",
                capability=ProcessingCapability.VISION,
                output={
                    "unprocessed_image_refs": list(
                        request.image_refs
                    )
                },
                visual_coverage=VisualCoverage.INCOMPLETE,
                warnings=[
                    (
                        "Visual content was detected but no vision "
                        "provider is configured. Images were not "
                        "silently ignored."
                    )
                ],
            )

        result = providers[0].process(request)

        if result.visual_coverage == VisualCoverage.NOT_APPLICABLE:
            result = result.model_copy(
                update={
                    "visual_coverage": VisualCoverage.UNKNOWN,
                    "warnings": [
                        *result.warnings,
                        (
                            "Vision provider did not explicitly report "
                            "visual coverage."
                        ),
                    ],
                }
            )

        return result
