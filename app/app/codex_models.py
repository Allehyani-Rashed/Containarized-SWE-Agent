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
        id="gpt-5-codex",
        label="GPT-5 Codex",
        description="Latest Codex-tuned GPT model with configurable reasoning effort.",
        is_default=True,
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


CODEX_REASONING_EFFORTS: tuple[str, ...] = ("low", "medium", "high")


def valid_reasoning_efforts() -> set[str]:
    return set(CODEX_REASONING_EFFORTS)


def default_reasoning_effort() -> str:
    return "medium"
