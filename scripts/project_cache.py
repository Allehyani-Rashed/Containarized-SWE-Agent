#!/usr/bin/env python3
"""Maintain GitLab project cache clones outside the task lifecycle."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlmodel import Session, select

from app.app.database import engine, init_db
from app.app.integrations import get_gitlab_pat_token
from app.app.models import Project
from app.app.project_cache import (
    ProjectCacheError,
    ProjectCacheService,
)

CACHE_SERVICE = ProjectCacheService()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect or refresh the cached GitLab repositories registered with the orchestrator.",
    )
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="Bootstrap project cache clones when missing.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh project cache clones.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Discard local cache modifications when refreshing.",
    )
    parser.add_argument(
        "--project-id",
        action="append",
        dest="project_ids",
        type=int,
        help="Limit the refresh to the specified project id (repeatable).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip network mutations while logging the intended git operations.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _format_project_label(project: Project) -> str:
    identifier = f"{project.id}" if project.id is not None else "<unpersisted>"
    path = project.gitlab_project_path or project.name or "<unknown>"
    host = project.gitlab_host or "<host>"
    return f"{identifier} ({host}/{path})"


def _collect_projects(session: Session, project_ids: list[int] | None) -> list[Project]:
    query = select(Project).order_by(Project.id)
    if project_ids:
        query = query.where(Project.id.in_(project_ids))
    return list(session.exec(query).all())


def _select_gitlab_token(project: Project, gitlab_pat: str | None) -> str | None:
    token = (gitlab_pat or "") or (project.gitlab_token or "")
    token = token.strip()
    return token or None


def _bootstrap_single_project(
    project: Project,
    *,
    gitlab_pat: str | None,
    dry_run: bool,
) -> bool:
    label = _format_project_label(project)
    token = _select_gitlab_token(project, gitlab_pat)
    if not token and not dry_run:
        print(
            f"[project {label}] GitLab credential missing; store a PAT via Settings -> Integrations",
            file=sys.stderr,
        )
        return False

    cache_path = CACHE_SERVICE.repo_path_for(project.gitlab_host or "", project.gitlab_project_path or "")
    cache_identifier = CACHE_SERVICE.identifier_for(project.gitlab_host or "", project.gitlab_project_path or "")

    def _log(message: str) -> None:
        print(f"[project {label}] {message}")

    _log("Starting bootstrap")

    try:
        CACHE_SERVICE.bootstrap(
            gitlab_host=project.gitlab_host or "",
            project_path=project.gitlab_project_path or "",
            default_branch=project.default_branch or "",
            gitlab_token=token,
            dry_run=dry_run,
            log_fn=_log,
        )
    except ProjectCacheError as exc:
        print(f"[project {label}] Bootstrap failed: {exc}", file=sys.stderr)
        return False

    _log("Bootstrap complete")
    return True


def _refresh_single_project(
    project: Project,
    *,
    gitlab_pat: str | None,
    dry_run: bool,
    force: bool,
) -> bool:
    label = _format_project_label(project)
    token = _select_gitlab_token(project, gitlab_pat)
    if not token and not dry_run:
        print(
            f"[project {label}] GitLab credential missing; store a PAT via Settings -> Integrations",
            file=sys.stderr,
        )
        return False

    cache_path = CACHE_SERVICE.repo_path_for(project.gitlab_host or "", project.gitlab_project_path or "")
    cache_identifier = CACHE_SERVICE.identifier_for(project.gitlab_host or "", project.gitlab_project_path or "")

    def _log(message: str) -> None:
        print(f"[project {label}] {message}")

    _log("Starting refresh")

    try:
        commit_hash = CACHE_SERVICE.refresh(
            gitlab_host=project.gitlab_host or "",
            project_path=project.gitlab_project_path or "",
            default_branch=project.default_branch or "",
            gitlab_token=token,
            dry_run=dry_run,
            force=force,
            log_fn=_log,
            identifier_override=cache_identifier,
        )
        CACHE_SERVICE.enforce_policy(
            gitlab_host=project.gitlab_host or "",
            project_path=project.gitlab_project_path or "",
            quota_mb=project.cache_quota_mb,
            prune_after_hours=project.cache_prune_after_hours,
            dry_run=dry_run,
            log_fn=_log,
        )
        snapshot_outcome = CACHE_SERVICE.snapshot(
            gitlab_host=project.gitlab_host or "",
            project_path=project.gitlab_project_path or "",
            commit_hash=commit_hash,
            branch=project.default_branch or "",
            dry_run=dry_run,
            log_fn=_log,
        )
        if snapshot_outcome.created_path is not None and not dry_run:
            _log(f"Snapshot stored at {snapshot_outcome.created_path}")
    except ProjectCacheError as exc:
        print(f"[project {label}] Refresh failed: {exc}", file=sys.stderr)
        return False

    short_hash = commit_hash[:12]
    _log(f"Refresh complete; HEAD at {project.default_branch}@{short_hash}")
    return True


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.bootstrap and not args.refresh:
        print("error: no action specified; pass --bootstrap and/or --refresh", file=sys.stderr)
        return 1

    init_db()

    dry_run = bool(args.dry_run) or _is_truthy(os.environ.get("RUNNER_GIT_DRY_RUN"))
    project_ids = list(dict.fromkeys(args.project_ids or []))

    with Session(engine) as session:
        projects = _collect_projects(session, project_ids or None)

        if project_ids:
            found_ids = {project.id for project in projects if project.id is not None}
            missing = [pid for pid in project_ids if pid not in found_ids]
            for pid in missing:
                print(f"warning: project id {pid} not found", file=sys.stderr)

        if not projects:
            print("No projects registered; nothing to refresh")
            return 0

        gitlab_pat = get_gitlab_pat_token(session)

        had_failures = False
        for project in projects:
            bootstrapped = True
            if args.bootstrap:
                bootstrapped = _bootstrap_single_project(project, gitlab_pat=gitlab_pat, dry_run=dry_run)
                if not bootstrapped:
                    had_failures = True

            if args.refresh and (bootstrapped or not args.bootstrap):
                succeeded = _refresh_single_project(
                    project,
                    gitlab_pat=gitlab_pat,
                    dry_run=dry_run,
                    force=bool(args.force),
                )
                if not succeeded:
                    had_failures = True

    return 1 if had_failures else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
