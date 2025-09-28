from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CodexModelInfo:
    id: str
    label: str
    description: str
    is_default: bool = False


CODEX_MODELS: tuple[CodexModelInfo, ...] = (
    CodexModelInfo(
        id="gpt-4o-mini",
        label="GPT-4o Mini",
        description="Fast, general-purpose model suitable for most task automation runs.",
        is_default=True,
    ),
    CodexModelInfo(
        id="gpt-4o",
        label="GPT-4o",
        description="Higher quality reasoning with increased latency and cost profile.",
    ),
    CodexModelInfo(
        id="o1-preview",
        label="o1 Preview",
        description="Experimental preview model for advanced planning workflows.",
    ),
)


def valid_model_ids() -> set[str]:
    return {model.id for model in CODEX_MODELS}


def default_model_id() -> str | None:
    for model in CODEX_MODELS:
        if model.is_default:
            return model.id
    return None


def iter_models() -> Iterable[CodexModelInfo]:
    return CODEX_MODELS
