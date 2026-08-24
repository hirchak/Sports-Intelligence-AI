from __future__ import annotations


class ProviderError(Exception):
    """Base class for normalized provider failures.

    `status_code` carries the HTTP status when the failure originates
    from a response (None for transport/timeout failures). The request
    ledger persists this value as telemetry.
    """

    status_code: int | None = None

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


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


class ProviderMappingError(ProviderError):
    """External identity resolution failed (no match or ambiguous).
    Non-retryable without new information; never guess."""


RETRYABLE_PROVIDER_ERRORS = (
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderTransportError,
)
