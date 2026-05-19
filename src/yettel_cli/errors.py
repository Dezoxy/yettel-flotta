from __future__ import annotations


class YettelError(RuntimeError):
    """Base exception for user-facing Yettel CLI errors."""


class AuthenticationError(YettelError):
    """Raised when login fails."""


class PhoneNotFoundError(YettelError):
    """Raised when the requested phone number is not present in the portal."""


class PortalLayoutError(YettelError):
    """Raised when the portal HTML no longer matches the expected structure."""


class PortalRequestError(YettelError):
    """Raised when the portal cannot be reached or returns an unexpected HTTP error."""


class SessionExpiredError(YettelError):
    """Raised when the saved cookies are missing or no longer authenticated."""
