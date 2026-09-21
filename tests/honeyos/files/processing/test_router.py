from honeyos.files.processing.base import (
    TextModelProvider,
    VisionProvider,
)
from honeyos.files.processing.models import (
    ProcessingCapability,
    ProcessingRequest,
    ProcessingResult,
    ProcessingStatus,
    VisualCoverage,
)
from honeyos.files.processing.registry import ProviderRegistry
from honeyos.files.processing.router import TaskRouter


class FakeTextProvider(TextModelProvider):
    @property
    def provider_id(self) -> str:
        return "fake-text"

    def process(self, request: ProcessingRequest) -> ProcessingResult:
        return ProcessingResult(
            status=ProcessingStatus.COMPLETE,
            provider_id=self.provider_id,
            capability=ProcessingCapability.TEXT,
            output={"text": request.text},
        )


class FakeVisionProvider(VisionProvider):
    @property
    def provider_id(self) -> str:
        return "fake-vision"

    def process(self, request: ProcessingRequest) -> ProcessingResult:
        return ProcessingResult(
            status=ProcessingStatus.COMPLETE,
            provider_id=self.provider_id,
            capability=ProcessingCapability.VISION,
            output={"processed": list(request.image_refs)},
            visual_coverage=VisualCoverage.COMPLETE,
        )


class BadCoverageVisionProvider(VisionProvider):
    @property
    def provider_id(self) -> str:
        return "bad-coverage-vision"

    def process(self, request: ProcessingRequest) -> ProcessingResult:
        return ProcessingResult(
            status=ProcessingStatus.COMPLETE,
            provider_id=self.provider_id,
            capability=ProcessingCapability.VISION,
            output={},
        )


def test_missing_text_provider_is_explicit():
    router = TaskRouter(ProviderRegistry())

    result = router.route_text(
        ProcessingRequest(
            attachment_id="att_test",
            task_type="normalize_text",
            text="hello",
        )
    )

    assert result.status == ProcessingStatus.UNAVAILABLE
    assert result.provider_id == "none"
    assert result.capability == ProcessingCapability.TEXT


def test_text_task_routes_to_text_provider():
    registry = ProviderRegistry()
    registry.register(FakeTextProvider())

    router = TaskRouter(registry)

    result = router.route_text(
        ProcessingRequest(
            attachment_id="att_test",
            task_type="normalize_text",
            text="hello",
        )
    )

    assert result.status == ProcessingStatus.COMPLETE
    assert result.provider_id == "fake-text"
    assert result.output["text"] == "hello"


def test_no_images_requires_no_vision_provider():
    router = TaskRouter(ProviderRegistry())

    result = router.route_vision(
        ProcessingRequest(
            attachment_id="att_test",
            task_type="understand_images",
        )
    )

    assert result.status == ProcessingStatus.COMPLETE
    assert result.visual_coverage == VisualCoverage.NOT_APPLICABLE


def test_images_without_vision_provider_are_not_silently_ignored():
    router = TaskRouter(ProviderRegistry())

    result = router.route_vision(
        ProcessingRequest(
            attachment_id="att_test",
            task_type="understand_images",
            image_refs=[
                "slide-3-image-1",
                "slide-3-image-2",
            ],
        )
    )

    assert result.status == ProcessingStatus.UNAVAILABLE
    assert result.visual_coverage == VisualCoverage.INCOMPLETE

    assert result.output["unprocessed_image_refs"] == [
        "slide-3-image-1",
        "slide-3-image-2",
    ]

    assert result.warnings


def test_images_route_to_vision_provider():
    registry = ProviderRegistry()
    registry.register(FakeVisionProvider())

    router = TaskRouter(registry)

    result = router.route_vision(
        ProcessingRequest(
            attachment_id="att_test",
            task_type="understand_images",
            image_refs=["slide-1-image-1"],
        )
    )

    assert result.status == ProcessingStatus.COMPLETE
    assert result.provider_id == "fake-vision"
    assert result.visual_coverage == VisualCoverage.COMPLETE


def test_vision_provider_must_report_meaningful_coverage():
    registry = ProviderRegistry()
    registry.register(BadCoverageVisionProvider())

    router = TaskRouter(registry)

    result = router.route_vision(
        ProcessingRequest(
            attachment_id="att_test",
            task_type="understand_images",
            image_refs=["slide-1-image-1"],
        )
    )

    assert result.status == ProcessingStatus.COMPLETE
    assert result.visual_coverage == VisualCoverage.UNKNOWN
    assert result.warnings
