"""Exceptions for qubopy."""


class QuboError(Exception):
    """Base exception for all qubopy errors."""


class QuboAuthError(QuboError):
    """Raised when authentication fails or credentials are invalid."""


class QuboConnectionError(QuboError):
    """Raised when communication with Qubo cloud fails or times out."""


class QuboDeviceNotFoundError(QuboError):
    """Raised when a requested device is not found in the account."""


class QuboCommandError(QuboError):
    """Raised when a command or shadow attribute update is rejected."""


class QuboKeyExtractionError(QuboError):
    """Raised when BLE cryptographic keys cannot be extracted or are missing."""
