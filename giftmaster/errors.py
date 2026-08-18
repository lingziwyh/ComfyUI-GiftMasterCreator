"""Public exception types."""


class GiftMasterError(RuntimeError):
    """Raised when a GiftMaster request is invalid or cannot be completed."""


class ConfigurationError(GiftMasterError):
    """Raised before a request when API configuration is unsafe or incomplete."""


class APIError(GiftMasterError):
    """Raised for a provider or transport failure."""


class SkillError(GiftMasterError):
    """Raised when a Skill package is invalid or cannot be routed safely."""


class ValidationError(GiftMasterError):
    """Raised when generated H3 text violates the selected contract."""
