"""What produced a result: application version, prompt version, model, and mode.

The prompt version is a hash of the prompt text, so any edit to a prompt shows up in every
result and in /health without anyone remembering to bump a number. In rules mode no model is
called, so `model` and `client` are null, but the prompt set is still the deployment's: a request
handled during a containment says which prompts the deployment runs, and a switch to rules mode
is not mistaken for a release.
"""
import hashlib

from . import model
from .config import Settings

APP_VERSION = "2.1.0"


def prompt_version(variant: str = "v1") -> str:
    classify_system, draft_system = model.prompts(variant)
    payload = (classify_system + "\n" + draft_system + "\n" + model.DATA_RULE).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


def versions(settings: Settings) -> dict:
    return {
        "app": APP_VERSION,
        "mode": settings.mode,
        "model": settings.model if settings.mode == "model" else None,
        "prompt": prompt_version(settings.prompt_variant),
        "prompt_variant": settings.prompt_variant,
        "client": settings.llm_client if settings.mode == "model" else None,
    }
