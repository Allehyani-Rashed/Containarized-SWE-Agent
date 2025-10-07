from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter(tags=["diagnostics"])


@router.get("/metrics")
def metrics_endpoint() -> Response:
    payload = generate_latest()
    return Response(payload, media_type=CONTENT_TYPE_LATEST)


@router.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True}


__all__ = ["router"]
