"""
CRM adapter error hierarchy.
Raised by CRMAdapter implementations so callers don't need to know
which CRM is underneath.
"""


class CRMError(Exception):
    """Base error for all CRM adapter failures."""

    def __init__(self, message: str, crm: str = "unknown", status_code: int | None = None):
        super().__init__(message)
        self.crm = crm
        self.status_code = status_code


class CRMAuthError(CRMError):
    """Token expired, revoked, or invalid — caller should re-authenticate."""


class CRMRateLimitError(CRMError):
    """CRM API rate limit hit — caller should back off and retry."""


class CRMNotFoundError(CRMError):
    """Requested record does not exist in the CRM."""
