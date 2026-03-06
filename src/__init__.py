"""Social Media Content Generator - Generate tech content for social media platforms."""

__version__ = "2.0.0"

from src.pipeline import ContentPipeline
from src.config import load_config
from src.constants import KEYWORDS, ULTIMATE_FALLBACK_DEFAULTS

__all__ = [
    'ContentPipeline',
    'load_config',
    'KEYWORDS',
    'ULTIMATE_FALLBACK_DEFAULTS',
]
