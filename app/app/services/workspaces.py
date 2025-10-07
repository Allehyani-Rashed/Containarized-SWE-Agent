from __future__ import annotations

import logging
import shutil
from pathlib import Path


logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACES_ROOT = REPO_ROOT / "workspaces"


def remove_workspace(path_str: str | None) -> None:
    if not path_str:
        return

    try:
        candidate = Path(path_str).resolve()
    except OSError as exc:
        logger.warning("Unable to resolve workspace path %s: %s", path_str, exc)
        return

    try:
        workspace_root = WORKSPACES_ROOT.resolve()
    except OSError as exc:
        logger.warning("Unable to resolve workspaces root %s: %s", WORKSPACES_ROOT, exc)
        return

    try:
        candidate.relative_to(workspace_root)
    except ValueError:
        return

    if candidate.is_dir():
        try:
            shutil.rmtree(candidate)
        except FileNotFoundError:
            return
        except OSError as exc:
            logger.warning("Failed to remove workspace directory %s: %s", candidate, exc)
    else:
        try:
            candidate.unlink()
        except FileNotFoundError:
            return
        except OSError as exc:
            logger.warning("Failed to remove workspace file %s: %s", candidate, exc)


__all__ = ["REPO_ROOT", "WORKSPACES_ROOT", "remove_workspace"]
