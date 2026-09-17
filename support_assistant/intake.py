import json
import re
from pathlib import Path

from .models import SupportRequest

REQUIRED_FIELDS = ("id", "customer_name", "email", "subject", "body", "channel", "created_at")


def normalize_text(value: str) -> str:
    """Trim and collapse whitespace; keep the customer's original casing for the draft."""
    return re.sub(r"\s+", " ", value).strip()


def parse_request(record: dict) -> SupportRequest:
    missing = [name for name in REQUIRED_FIELDS if name not in record]
    if missing:
        raise ValueError(f"request {record.get('id', '?')} is missing fields: {', '.join(missing)}")
    return SupportRequest(
        id=str(record["id"]),
        customer_name=str(record["customer_name"]).strip(),
        email=str(record["email"]).strip(),
        subject=normalize_text(str(record["subject"])),
        body=normalize_text(str(record["body"])),
        channel=str(record["channel"]).strip().lower(),
        created_at=str(record["created_at"]),
    )


def load_requests(path: str | Path) -> list[SupportRequest]:
    """Read a JSONL file with one support request per line."""
    requests = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"line {line_number} is not valid JSON: {error}") from error
            requests.append(parse_request(record))
    return requests
