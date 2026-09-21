import pytest

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
from honeyos.files.processing.registry import (
    ProviderRegistry,
    ProviderRegistryError,
)


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
            output={"images": request.image_refs},
            visual_coverage=VisualCoverage.COMPLETE,
        )


def test_empty_registry_requires_no_model():
    registry = ProviderRegistry()

    assert registry.list_ids() == []
    assert registry.providers_for(ProcessingCapability.TEXT) == []
    assert registry.providers_for(ProcessingCapability.VISION) == []


def test_register_text_provider():
    registry = ProviderRegistry()
    provider = FakeTextProvider()

    registry.register(provider)

    assert registry.get("fake-text") is provider
    assert registry.providers_for(
        ProcessingCapability.TEXT
    ) == [provider]

    assert registry.providers_for(
        ProcessingCapability.VISION
    ) == []


def test_register_vision_provider():
    registry = ProviderRegistry()
    provider = FakeVisionProvider()

    registry.register(provider)

    assert registry.providers_for(
        ProcessingCapability.VISION
    ) == [provider]


def test_duplicate_provider_rejected():
    registry = ProviderRegistry()

    registry.register(FakeTextProvider())

    with pytest.raises(ProviderRegistryError):
        registry.register(FakeTextProvider())


def test_provider_can_be_replaced():
    registry = ProviderRegistry()

    first = FakeTextProvider()
    second = FakeTextProvider()

    registry.register(first)
    registry.register(second, replace=True)

    assert registry.get("fake-text") is second


def test_unregister_provider():
    registry = ProviderRegistry()

    registry.register(FakeTextProvider())

    assert registry.unregister("fake-text") is True
    assert registry.unregister("fake-text") is False


def test_missing_provider_raises():
    registry = ProviderRegistry()

    with pytest.raises(ProviderRegistryError):
        registry.get("missing")


def test_text_provider_process_contract():
    provider = FakeTextProvider()

    result = provider.process(
        ProcessingRequest(
            attachment_id="att_test",
            task_type="normalize_text",
            text="hello",
        )
    )

    assert result.status == ProcessingStatus.COMPLETE
    assert result.capability == ProcessingCapability.TEXT
    assert result.output["text"] == "hello"


def test_vision_provider_reports_visual_coverage():
    provider = FakeVisionProvider()

    result = provider.process(
        ProcessingRequest(
            attachment_id="att_test",
            task_type="understand_images",
            image_refs=["slide-1-image-1"],
        )
    )

    assert result.capability == ProcessingCapability.VISION
    assert result.visual_coverage == VisualCoverage.COMPLETE
