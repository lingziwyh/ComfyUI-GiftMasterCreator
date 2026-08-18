"""Model-independent core for the GiftMasterCreator ComfyUI extension."""

from .api import APIClient, APIConfig, GenerationSettings
from .errors import GiftMasterError
from .h3 import ValidationResult, validate_h3_prompt
from .tasks import (
    GiftTaskSpec,
    build_high_coin_task,
    build_low_coin_task,
    parse_task_spec,
    validate_task_spec,
    validate_image_count,
)

__all__ = [
    "APIClient",
    "APIConfig",
    "GenerationSettings",
    "GiftMasterError",
    "GiftTaskSpec",
    "ValidationResult",
    "build_high_coin_task",
    "build_low_coin_task",
    "parse_task_spec",
    "validate_h3_prompt",
    "validate_image_count",
    "validate_task_spec",
]
