from dataclasses import dataclass, field


@dataclass(frozen=True)
class SupportRequest:
    id: str
    customer_name: str
    email: str
    subject: str
    body: str
    channel: str
    created_at: str

    @property
    def text(self) -> str:
        """Subject and body together, as the text the assistant reasons about."""
        return f"{self.subject}\n{self.body}"


@dataclass(frozen=True)
class Article:
    slug: str
    title: str
    category: str
    keywords: tuple[str, ...]
    body: str

    @property
    def summary(self) -> str:
        """The first paragraph of the article, used inside drafts."""
        return self.body.strip().split("\n\n")[0].strip()


@dataclass
class Result:
    id: str
    category: str
    route: str
    reasons: list[str] = field(default_factory=list)
    article: str | None = None
    draft: str | None = None
    sent: bool = False
    confidence: float | None = None
