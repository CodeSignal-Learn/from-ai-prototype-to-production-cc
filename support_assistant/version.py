"""What produced a result: application version, prompt version, model, and mode.

The prompt version is a hash of the prompt text, so any edit to a prompt shows up in every
result and in /health without anyone remembering to bump a number.
"""
import hashlib

from . import model
from .config import Settings

APP_VERSION = "2.0.0"


def prompt_version() -> str:
    payload = (model.CLASSIFY_SYSTEM + "\n" + model.DRAFT_SYSTEM + "\n" + model.DATA_RULE).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


def versions(settings: Settings) -> dict:
    return {
        "app": APP_VERSION,
        "mode": settings.mode,
        "model": settings.model if settings.mode == "model" else None,
        "prompt": prompt_version() if settings.mode == "model" else None,
        "client": settings.llm_client if settings.mode == "model" else None,
    }
