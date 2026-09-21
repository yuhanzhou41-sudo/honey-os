from __future__ import annotations

from abc import ABC, abstractmethod

from honeyos.files.processing.models import (
    ProcessingCapability,
    ProcessingRequest,
    ProcessingResult,
)


class ProcessingProviderError(RuntimeError):
    pass


class ProviderUnavailableError(ProcessingProviderError):
    pass


class ProcessingProvider(ABC):
    """Base interface for pluggable HoneyOS processing providers."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def capabilities(self) -> frozenset[ProcessingCapability]:
        raise NotImplementedError

    def supports(self, capability: ProcessingCapability) -> bool:
        return capability in self.capabilities

    @abstractmethod
    def process(
        self,
        request: ProcessingRequest,
    ) -> ProcessingResult:
        raise NotImplementedError


class TextModelProvider(ProcessingProvider):
    @property
    def capabilities(self) -> frozenset[ProcessingCapability]:
        return frozenset({ProcessingCapability.TEXT})


class VisionProvider(ProcessingProvider):
    @property
    def capabilities(self) -> frozenset[ProcessingCapability]:
        return frozenset({ProcessingCapability.VISION})
