from __future__ import annotations

from honeyos.files.processing.base import ProcessingProvider
from honeyos.files.processing.models import ProcessingCapability


class ProviderRegistryError(RuntimeError):
    pass


class ProviderRegistry:
    """Registry only.

    Model selection policy belongs to TaskRouter, not to this class.
    """

    def __init__(self) -> None:
        self._providers: dict[str, ProcessingProvider] = {}

    def register(
        self,
        provider: ProcessingProvider,
        *,
        replace: bool = False,
    ) -> None:
        provider_id = provider.provider_id.strip()

        if not provider_id:
            raise ProviderRegistryError("provider_id must not be blank")

        if provider_id in self._providers and not replace:
            raise ProviderRegistryError(
                f"provider {provider_id!r} is already registered"
            )

        self._providers[provider_id] = provider

    def unregister(self, provider_id: str) -> bool:
        return self._providers.pop(provider_id, None) is not None

    def get(self, provider_id: str) -> ProcessingProvider:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise ProviderRegistryError(
                f"provider {provider_id!r} is not registered"
            ) from exc

    def providers_for(
        self,
        capability: ProcessingCapability,
    ) -> list[ProcessingProvider]:
        return [
            provider
            for provider in self._providers.values()
            if provider.supports(capability)
        ]

    def list_ids(self) -> list[str]:
        return list(self._providers)
