class LeadPilotError(Exception):
    """Base class for expected application errors."""


class ConfigurationError(LeadPilotError):
    """Raised when application configuration is invalid."""


class DatabaseUnavailableError(LeadPilotError):
    """Raised when persistence cannot be reached."""
