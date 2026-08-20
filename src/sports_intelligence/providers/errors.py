from __future__ import annotations


class ProviderError(Exception):
    """Base class for normalized provider failures."""


class ProviderConfigError(ProviderError):
    """Invalid provider configuration (e.g. unknown provider name). Non-retryable."""


class ProviderAuthError(ProviderError):
    """Authentication/authorization failure (401/403). Non-retryable."""


class ProviderRateLimitError(ProviderError):
    """Provider rate limit (429). Retryable."""


class ProviderServerError(ProviderError):
    """Provider 5xx response. Retryable."""


class ProviderTimeoutError(ProviderError):
    """Network timeout. Retryable."""


class ProviderTransportError(ProviderError):
    """Generic transport failure. Retryable."""


class ProviderResponseError(ProviderError):
    """Malformed/unexpected response payload. Non-retryable."""


RETRYABLE_PROVIDER_ERRORS = (
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderTransportError,
)
