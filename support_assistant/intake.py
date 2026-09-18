import json
import re
from pathlib import Path

from .models import SupportRequest
from .security import mask_sensitive

REQUIRED_FIELDS = ("id", "customer_name", "email", "subject", "body", "channel", "created_at")
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CHANNELS = ("email", "web_form", "chat")
MAX_BODY_CHARS = 4000

OVERSIZED = "oversized"
SENSITIVE_MASKED = "sensitive_data_masked"


class IntakeError(ValueError):
    """A record that cannot become a request."""


def normalize_text(value: str) -> str:
    """Trim, collapse whitespace, and lowercase text so keyword rules match reliably."""
    return re.sub(r"\s+", " ", value).strip().lower()


def parse_request(record: dict) -> SupportRequest:
    """Validate one record and turn it into a request. Raises IntakeError when it cannot.

    Card-like numbers are masked here, so nothing downstream, including the model, sees them.
    A body over MAX_BODY_CHARS is kept whole but flagged; the pipeline sends it to a person.
    """
    if not isinstance(record, dict):
        raise IntakeError("record is not an object")
    missing = [name for name in REQUIRED_FIELDS if name not in record or record[name] is None]
    if missing:
        raise IntakeError(f"request {record.get('id', '?')} is missing fields: {', '.join(missing)}")
    request_id = str(record["id"]).strip()
    if not ID_PATTERN.match(request_id):
        raise IntakeError(f"request id {request_id!r} is not a valid id")
    email = str(record["email"]).strip()
    if not EMAIL_PATTERN.match(email):
        raise IntakeError(f"request {request_id} has an invalid email address")
    channel = str(record["channel"]).strip().lower()
    if channel not in CHANNELS:
        raise IntakeError(f"request {request_id} has unknown channel {channel!r}")
    subject, masked_subject = mask_sensitive(normalize_text(str(record["subject"])))
    body, masked_body = mask_sensitive(normalize_text(str(record["body"])))
    if not body:
        raise IntakeError(f"request {request_id} has an empty body")
    flags = []
    if masked_subject or masked_body:
        flags.append(SENSITIVE_MASKED)
    if len(body) > MAX_BODY_CHARS:
        flags.append(OVERSIZED)
    return SupportRequest(
        id=request_id,
        customer_name=str(record["customer_name"]).strip(),
        email=email,
        subject=subject,
        body=body,
        channel=channel,
        created_at=str(record["created_at"]),
        flags=tuple(flags),
    )


def load_requests(path: str | Path, rejected: list | None = None) -> list[SupportRequest]:
    """Read a JSONL file with one support request per line.

    Records that cannot become requests are collected in `rejected` as (line number, reason)
    when a list is given, and skipped; without a list the first bad record raises.
    """
    requests = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                requests.append(parse_request(json.loads(line)))
            except (json.JSONDecodeError, IntakeError) as error:
                if rejected is None:
                    raise IntakeError(f"line {line_number}: {error}") from error
                rejected.append((line_number, str(error)))
    return requests
