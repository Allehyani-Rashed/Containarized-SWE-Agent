from __future__ import annotations

from typing import List

from fastapi import APIRouter

from ..codex_models import iter_models
from ..schemas import CodexModelSummary

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=List[CodexModelSummary])
def list_codex_models() -> List[CodexModelSummary]:
    return [
        CodexModelSummary(
            id=model.id,
            label=model.label,
            description=model.description,
            is_default=model.is_default,
        )
        for model in iter_models()
    ]


__all__ = ["router"]
