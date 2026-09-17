import re
from pathlib import Path

from .models import Article

FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def parse_article(path: Path) -> Article:
    match = FRONT_MATTER.match(path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"{path.name} has no front matter")
    header, body = match.groups()
    fields = {}
    for line in header.splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    keywords = tuple(keyword.strip().lower() for keyword in fields.get("keywords", "").split(",") if keyword.strip())
    return Article(
        slug=path.stem,
        title=fields["title"],
        category=fields["category"],
        keywords=keywords,
        body=body,
    )


def load_articles(folder: str | Path) -> list[Article]:
    """Read every Markdown article in the knowledge-base folder."""
    return [parse_article(path) for path in sorted(Path(folder).glob("*.md"))]


def find_article(articles: list[Article], category: str, text: str) -> Article | None:
    """Pick the article in the request's category whose keywords best match the text."""
    candidates = [article for article in articles if article.category == category]
    if not candidates:
        return None
    scored = sorted(
        candidates,
        key=lambda article: sum(1 for keyword in article.keywords if keyword in text),
        reverse=True,
    )
    return scored[0]
