"""The rubric as data: criteria, their kind, and the verdicts each one allows.

`evals/rubric.md` is the text people read and agree on; `evals/rubric.json` is the same rubric
in a form code can check against. Loading validates that the two still describe the same
criteria, so an edit to one without the other fails fast.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
RUBRIC_JSON = EVALS_DIR / "rubric.json"
RUBRIC_MD = EVALS_DIR / "rubric.md"

DETERMINISTIC = "deterministic"
JUDGED = "judged"
HEADING = re.compile(r"^### (R\d+) (.+?) \((deterministic|judged)\)\s*$", re.MULTILINE)


class RubricError(ValueError):
    """The rubric files disagree with each other or with the shape code expects."""


@dataclass(frozen=True)
class Criterion:
    id: str
    name: str
    kind: str
    applies_to: str
    verdicts: tuple[str, ...]
    statement: str
    evidence: str | None = None


@dataclass(frozen=True)
class Rubric:
    version: str
    criteria: tuple[Criterion, ...]
    acceptable_rule: str
    blocking: tuple[str, ...]

    def get(self, criterion_id: str) -> Criterion:
        for criterion in self.criteria:
            if criterion.id == criterion_id:
                return criterion
        raise KeyError(criterion_id)

    @property
    def deterministic(self) -> tuple[Criterion, ...]:
        return tuple(c for c in self.criteria if c.kind == DETERMINISTIC)

    @property
    def judged(self) -> tuple[Criterion, ...]:
        return tuple(c for c in self.criteria if c.kind == JUDGED)

    def acceptable(self, verdicts: dict) -> bool:
        """Apply the acceptance rule to one result's verdicts, keyed by criterion id."""
        for criterion in self.criteria:
            verdict = verdicts.get(criterion.id)
            if verdict not in criterion.verdicts:
                raise RubricError(f"{criterion.id} verdict {verdict!r} is not one of {criterion.verdicts}")
        if verdicts["R1"] != "pass" or verdicts["R2"] != "pass" or verdicts["R5"] != "pass":
            return False
        if verdicts["R3"] != "pass":
            return False
        return verdicts["R4"] in ("pass", "partial")


def load_rubric(json_path: Path = RUBRIC_JSON, md_path: Path = RUBRIC_MD) -> Rubric:
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    criteria = []
    for raw in data["criteria"]:
        if raw["kind"] not in (DETERMINISTIC, JUDGED):
            raise RubricError(f"{raw['id']} has unknown kind {raw['kind']!r}")
        if raw["kind"] == JUDGED and not raw.get("evidence"):
            raise RubricError(f"{raw['id']} is judged and must say what evidence a verdict carries")
        criteria.append(Criterion(
            id=raw["id"], name=raw["name"], kind=raw["kind"], applies_to=raw["applies_to"],
            verdicts=tuple(raw["verdicts"]), statement=raw["statement"], evidence=raw.get("evidence"),
        ))
    ids = [c.id for c in criteria]
    if len(set(ids)) != len(ids):
        raise RubricError("criterion ids repeat")
    blocking = tuple(data["acceptable"]["blocking"])
    for criterion_id in blocking:
        if criterion_id not in ids:
            raise RubricError(f"blocking criterion {criterion_id} is not defined")
    rubric = Rubric(version=str(data["version"]), criteria=tuple(criteria),
                    acceptable_rule=data["acceptable"]["rule"], blocking=blocking)
    check_against_markdown(rubric, Path(md_path).read_text(encoding="utf-8"))
    return rubric


def check_against_markdown(rubric: Rubric, markdown: str) -> None:
    """The headings in rubric.md must list the same criteria, names, and kinds as rubric.json."""
    in_text = {m.group(1): (m.group(2), m.group(3)) for m in HEADING.finditer(markdown)}
    in_json = {c.id: (c.name, c.kind) for c in rubric.criteria}
    if in_text != in_json:
        only_text = sorted(set(in_text) - set(in_json))
        only_json = sorted(set(in_json) - set(in_text))
        differing = sorted(k for k in set(in_text) & set(in_json) if in_text[k] != in_json[k])
        raise RubricError(
            f"rubric.md and rubric.json disagree: only in md {only_text}, only in json {only_json}, differing {differing}"
        )
