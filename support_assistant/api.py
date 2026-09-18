"""HTTP interface: one request, a batch, and a health check.

The app is built by a factory so tests can pass their own settings and client. Nothing here
decides anything about a request; it validates input, calls the pipeline, and returns results.

The two endpoints that take customer text require the service key (`ASSISTANT_API_KEY`) in an
`X-API-Key` header; `/health` stays open so operators and load balancers can read it. The served
entry point refuses to start without a key. Tests may build an app without one.
"""
import hmac
from dataclasses import asdict

from fastapi import Depends, FastAPI, Header, HTTPException

from .config import Settings, load_settings
from .intake import IntakeError, parse_request
from .knowledge import load_articles
from .llm.client import LLMClient
from .llm.factory import build_client
from .pipeline import process_batch, process_request

MAX_BATCH = 200


def create_app(settings: Settings, articles=None, client: LLMClient | None = None) -> FastAPI:
    articles = load_articles(settings.knowledge_dir) if articles is None else articles
    if client is None and settings.mode == "model":
        client = build_client(settings)
    app = FastAPI(title="Fernwood support-request assistant", version="2")

    def require_key(x_api_key: str | None = Header(default=None)) -> None:
        if settings.api_key is None:
            return
        if x_api_key is None or not hmac.compare_digest(x_api_key, settings.api_key):
            raise HTTPException(status_code=401, detail="missing or invalid API key")

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "mode": settings.mode,
            "llm_client": settings.llm_client if settings.mode == "model" else None,
            "model": settings.model if settings.mode == "model" else None,
            "concurrency": settings.concurrency,
            "articles": len(articles),
        }

    @app.post("/requests", dependencies=[Depends(require_key)])
    def one_request(record: dict):
        try:
            request = parse_request(record)
        except IntakeError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return asdict(process_request(request, articles, settings, client))

    @app.post("/batches", dependencies=[Depends(require_key)])
    def batch(records: list[dict]):
        if len(records) > MAX_BATCH:
            raise HTTPException(status_code=413, detail=f"at most {MAX_BATCH} requests per batch")
        requests, rejected = [], []
        for index, record in enumerate(records):
            try:
                requests.append(parse_request(record))
            except IntakeError as error:
                rejected.append({"index": index, "reason": str(error)})
        results = process_batch(requests, articles, settings, client)
        return {"results": [asdict(result) for result in results], "rejected": rejected}

    return app


def app_factory() -> FastAPI:
    """Entry point for `uvicorn support_assistant.api:app_factory --factory`."""
    settings = load_settings()
    if not settings.api_key:
        raise RuntimeError("ASSISTANT_API_KEY must be set to serve the API; clients send it in the X-API-Key header")
    return create_app(settings)
