from .models import Article, SupportRequest

SIGN_OFF = "Best regards,\nFernwood Outfitters Support"


def first_name(customer_name: str) -> str:
    return customer_name.split()[0] if customer_name.strip() else "there"


def compose_draft(request: SupportRequest, article: Article) -> str:
    """Build a reply from the article's summary. The draft is for a human to review."""
    return (
        f"Hi {first_name(request.customer_name)},\n\n"
        f"Thanks for contacting Fernwood Outfitters about your {article.title.lower()} question.\n\n"
        f"{article.summary}\n\n"
        f"If anything is unclear, reply to this message and we will help.\n\n"
        f"{SIGN_OFF}"
    )
