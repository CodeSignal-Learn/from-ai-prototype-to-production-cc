from pathlib import Path

import pytest

from support_assistant.intake import parse_request
from support_assistant.knowledge import load_articles

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def articles():
    return load_articles(PROJECT_ROOT / "kb")


@pytest.fixture
def make_request():
    def _make(subject: str, body: str, customer_name: str = "Test Customer"):
        return parse_request(
            {
                "id": "REQ-TEST",
                "customer_name": customer_name,
                "email": "test@example.com",
                "subject": subject,
                "body": body,
                "channel": "email",
                "created_at": "2026-08-01T00:00:00Z",
            }
        )

    return _make
