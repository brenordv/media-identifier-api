"""Errors shared by the identification services."""

from typing import Literal

UpstreamService = Literal["tmdb", "openai"]
UpstreamReason = Literal["timeout", "connection", "rate_limited", "server_error", "invalid_response"]


class UpstreamUnavailableError(RuntimeError):
    """A service the answer depends on could not be reached or did not answer usably; retrying later may succeed.

    Args:
        service: The service that failed.
        reason: How it failed.
        code: The service's own error code, when it gave one (OpenAI's ``credit_balance_exhausted``, for example).
    """

    def __init__(self, service: UpstreamService, reason: UpstreamReason, code: str | None = None) -> None:
        super().__init__(f"{service} unavailable: {reason}" + (f" ({code})" if code else ""))
        self.service: UpstreamService = service
        self.reason: UpstreamReason = reason
        self.code = code

    @property
    def cause_label(self) -> str:
        """``"<service>: <reason>"``, followed by the service's code when there is one.

        For example ``"tmdb: timeout"`` or ``"openai: rate_limited credit_balance_exhausted"``.
        """
        label = f"{self.service}: {self.reason}"
        return f"{label} {self.code}" if self.code else label
