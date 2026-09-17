import os

from .models import SupportRequest

WEBHOOK_URL = os.environ.get("FERNWOOD_WEBHOOK_URL", "")


def send_draft(request: SupportRequest, draft: str) -> None:
    """Post a finished draft to the support inbox webhook so it goes out immediately."""
    if not WEBHOOK_URL:
        return
    import requests

    requests.post(WEBHOOK_URL, json={"to": request.email, "body": draft}, timeout=5)
