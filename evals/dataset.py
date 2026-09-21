"""Evaluation cases: what was asked, what should happen, and what an acceptable reply must and
must not say.

A dataset is a versioned folder under evals/datasets/ holding cases.jsonl and manifest.json.
Cases never change inside a version; a new version is a new folder, so every evaluation run
names exactly the cases it saw. Loading validates the cases and the manifest, and refuses
fixtures that carry anything that looks like real customer data.

    python3 -m evals.dataset v1                   # validate and print coverage
    python3 -m evals.dataset v1 --write-manifest  # regenerate manifest.json after authoring
"""
import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from support_assistant.intake import IntakeError, parse_request
from support_assistant.models import SupportRequest
from support_assistant.security import CATEGORIES

DATASETS_DIR = Path(__file__).resolve().parent / "datasets"
SPLITS = ("development", "held_out")
KINDS = ("realistic", "edge", "insufficient_information")
ROUTES = ("draft", "human_review")
TEST_CARD_DIGITS = "4111111111111111"
CARD_LIKE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
ALLOWED_EMAIL_DOMAIN = "@example.com"


class DatasetError(ValueError):
    """The cases or the manifest are not what the code expects."""


@dataclass(frozen=True)
class Case:
    id: str
    source: str
    split: str
    kind: str
    tags: tuple[str, ...]
    record: dict
    expected_category: str
    expected_route: str
    expected_article: str | None
    reply_must: str
    reply_must_not: str
    must_not_mention: tuple[str, ...]
    note: str

    @property
    def request(self) -> SupportRequest:
        return parse_request(self.record)


def dataset_dir(version: str) -> Path:
    return DATASETS_DIR / version


def read_cases(version: str) -> list[Case]:
    path = dataset_dir(version) / "cases.jsonl"
    cases = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as error:
            raise DatasetError(f"{path.name} line {line_number}: {error}") from error
        cases.append(Case(
            id=raw["id"], source=raw["source"], split=raw["split"], kind=raw["kind"], tags=tuple(raw.get("tags", [])),
            record=raw["request"], expected_category=raw["expected"]["category"], expected_route=raw["expected"]["route"],
            expected_article=raw["expected"].get("article"), reply_must=raw["reply_must"], reply_must_not=raw["reply_must_not"],
            must_not_mention=tuple(raw.get("must_not_mention", [])), note=raw.get("note", ""),
        ))
    return cases


def sensitive_problems(case: Case) -> list[str]:
    """Anything in a fixture that could be a real person's data. Synthetic markers are allowed."""
    problems = []
    if not case.record.get("email", "").endswith(ALLOWED_EMAIL_DOMAIN):
        problems.append(f"{case.id}: email is not under {ALLOWED_EMAIL_DOMAIN}")
    for field in ("subject", "body"):
        for match in CARD_LIKE.finditer(case.record.get(field, "")):
            if re.sub(r"[ -]", "", match.group()) != TEST_CARD_DIGITS:
                problems.append(f"{case.id}: {field} contains a card-like number that is not the test number")
    return problems


def validate_cases(cases: list[Case], article_slugs: set[str]) -> None:
    problems = []
    seen = set()
    for case in cases:
        if case.id in seen:
            problems.append(f"{case.id}: duplicate id")
        seen.add(case.id)
        if case.record.get("id") != case.id:
            problems.append(f"{case.id}: request id differs from case id")
        try:
            parse_request(case.record)
        except IntakeError as error:
            problems.append(f"{case.id}: request fails intake: {error}")
        if case.expected_category not in CATEGORIES:
            problems.append(f"{case.id}: unknown category {case.expected_category!r}")
        if case.expected_route not in ROUTES:
            problems.append(f"{case.id}: unknown route {case.expected_route!r}")
        if case.expected_route == "draft" and not case.expected_article:
            problems.append(f"{case.id}: a draft case needs the article that grounds it")
        if case.expected_article and case.expected_article not in article_slugs:
            problems.append(f"{case.id}: article {case.expected_article!r} is not in the knowledge base")
        if case.split not in SPLITS:
            problems.append(f"{case.id}: unknown split {case.split!r}")
        if case.kind not in KINDS:
            problems.append(f"{case.id}: unknown kind {case.kind!r}")
        if case.source.startswith("trial:") and case.split != "development":
            problems.append(f"{case.id}: trial cases were used to tune the prompts and must stay in development")
        if not case.reply_must.strip() or not case.reply_must_not.strip():
            problems.append(f"{case.id}: reply_must and reply_must_not are required")
        if any(phrase != phrase.lower() for phrase in case.must_not_mention):
            problems.append(f"{case.id}: must_not_mention phrases are matched lowercase and must be written lowercase")
        problems += sensitive_problems(case)
    if problems:
        raise DatasetError("\n".join(problems))


def coverage(cases: list[Case]) -> dict:
    return {
        "cases": len(cases),
        "by_split": dict(sorted(Counter(c.split for c in cases).items())),
        "by_kind": dict(sorted(Counter(c.kind for c in cases).items())),
        "by_route": dict(sorted(Counter(c.expected_route for c in cases).items())),
        "by_category": dict(sorted(Counter(c.expected_category for c in cases).items())),
        "by_split_category_route": {
            f"{split}/{category}/{route}": count
            for (split, category, route), count in sorted(Counter((c.split, c.expected_category, c.expected_route) for c in cases).items())
        },
        "tags": dict(sorted(Counter(tag for c in cases for tag in c.tags).items())),
    }


def build_manifest(version: str, cases: list[Case]) -> dict:
    digest = hashlib.sha256((dataset_dir(version) / "cases.jsonl").read_bytes()).hexdigest()
    return {"version": version, "cases_sha256": digest, **coverage(cases)}


def load_cases(version: str, split: str | None = None, article_slugs: set[str] | None = None) -> list[Case]:
    """Read, validate, and check the manifest of a dataset version; optionally one split."""
    if article_slugs is None:
        from support_assistant.knowledge import load_articles
        from support_assistant.config import Settings
        article_slugs = {a.slug for a in load_articles(Settings().knowledge_dir)}
    cases = read_cases(version)
    validate_cases(cases, article_slugs)
    manifest_path = dataset_dir(version) / "manifest.json"
    if not manifest_path.exists():
        raise DatasetError(f"{version} has no manifest.json; run python3 -m evals.dataset {version} --write-manifest")
    if json.loads(manifest_path.read_text(encoding="utf-8")) != build_manifest(version, cases):
        raise DatasetError(f"{version}/manifest.json does not describe cases.jsonl; regenerate it and review the change")
    if split is not None:
        if split not in SPLITS:
            raise DatasetError(f"unknown split {split!r}")
        cases = [c for c in cases if c.split == split]
    return cases


def coverage_table(cases: list[Case]) -> str:
    rows = Counter((c.expected_category, c.split, c.expected_route) for c in cases)
    lines = ["| Category | Development draft | Development person | Held-out draft | Held-out person | Total |",
             "| --- | --- | --- | --- | --- | --- |"]
    for category in CATEGORIES:
        counts = [rows[(category, s, r)] for s in SPLITS for r in ROUTES]
        lines.append(f"| {category} | " + " | ".join(str(n) for n in counts) + f" | {sum(counts)} |")
    totals = [sum(rows[(c, s, r)] for c in CATEGORIES) for s in SPLITS for r in ROUTES]
    lines.append("| **all** | " + " | ".join(str(n) for n in totals) + f" | {sum(totals)} |")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("version")
    parser.add_argument("--write-manifest", action="store_true")
    args = parser.parse_args(argv)
    from support_assistant.config import Settings
    from support_assistant.knowledge import load_articles
    slugs = {a.slug for a in load_articles(Settings().knowledge_dir)}
    cases = read_cases(args.version)
    validate_cases(cases, slugs)
    if args.write_manifest:
        (dataset_dir(args.version) / "manifest.json").write_text(json.dumps(build_manifest(args.version, cases), indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.version}/manifest.json")
    cases = load_cases(args.version, article_slugs=slugs)
    print(f"dataset {args.version}: {len(cases)} cases, valid")
    print(coverage_table(cases))
    cov = coverage(cases)
    print("\nkinds: " + ", ".join(f"{k} {v}" for k, v in cov["by_kind"].items()))
    print("tags: " + ", ".join(f"{k} {v}" for k, v in cov["tags"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
