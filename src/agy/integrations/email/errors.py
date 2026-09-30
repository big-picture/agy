"""Typed errors for outbound email (send, send draft, create draft).

All errors subclass :class:`RuntimeError`, so callers that catch
``RuntimeError`` (the historical contract) keep working. Messages keep the
historical prefixes (``"Failed to send email: ..."``, ``"Safety check failed:
..."``) for callers that match on strings.

Retry guidance:

- :class:`EmailTransientError` - the request was rejected before being
  processed (HTTP 429/503/504, connection refused/reset, connect timeout).
  Retrying later is reasonable; honour ``retry_after`` when set.
- :class:`EmailPermanentError` - retrying the same request will not help, or
  is unsafe. This includes ``requests.ReadTimeout``: the request reached the
  server and may have been accepted, so a blind retry can send a duplicate.
- :class:`EmailSafetyError` - a recipient is outside the configured allowlist.
"""

from __future__ import annotations

from collections.abc import Mapping


class EmailSendError(RuntimeError):
    """Base class for outbound email failures."""


class EmailTransientError(EmailSendError):
    """Outbound email failed in a way that is safe to retry later.

    Attributes:
        status_code: HTTP status code, or ``None`` for connection failures.
        retry_after: Seconds to wait before retrying (from ``Retry-After``),
            or ``None`` if the server did not say.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


class EmailPermanentError(EmailSendError):
    """Outbound email failed and must not be retried unchanged.

    Attributes:
        status_code: HTTP status code, or ``None`` when no response was received.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class EmailSafetyError(EmailPermanentError):
    """A recipient was rejected by the email safety allowlist."""


def parse_retry_after(headers: Mapping[str, str] | None) -> float | None:
    """Return ``Retry-After`` in seconds, or ``None`` if absent/not numeric.

    Only the delta-seconds form is supported; HTTP-date values yield ``None``.
    """
    if not headers:
        return None
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        seconds = float(str(raw).strip())
    except ValueError:
        return None
    return seconds if seconds >= 0 else None
