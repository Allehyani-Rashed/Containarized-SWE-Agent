#!/usr/bin/env python3
"""Helper to migrate legacy `.codexignore` files to `.projectsanitize`.

The sanitizer now prefers `.projectsanitize` and only falls back to
`.codexignore` during the deprecation window. This script renames (or merges)
legacy files so sanitized workspaces keep excluding large artefacts and secrets.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PRIMARY_FILENAME = ".projectsanitize"
LEGACY_FILENAME = ".codexignore"


def _read_lines(path: Path) -> list[str]:
    return [line.rstrip("\n") for line in path.read_text(encoding="utf-8").splitlines()]


def _merge_unique_lines(existing: list[str], incoming: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for source in (existing, incoming):
        for line in source:
            if line not in seen:
                seen.add(line)
                merged.append(line)
    return merged


def migrate(path: Path, *, dry_run: bool, force: bool, keep_legacy: bool) -> int:
    project_root = path.expanduser().resolve()
    if not project_root.exists() or not project_root.is_dir():
        print(f"error: target path {project_root} does not exist or is not a directory", file=sys.stderr)
        return 2

    primary_path = project_root / PRIMARY_FILENAME
    legacy_path = project_root / LEGACY_FILENAME

    if not legacy_path.exists():
        if primary_path.exists():
            print(f"ok: {project_root} already uses {PRIMARY_FILENAME}")
            return 0
        print(f"warning: no {LEGACY_FILENAME} found under {project_root}; nothing to migrate")
        return 0

    if primary_path.exists() and not force:
        print(
            f"error: {PRIMARY_FILENAME} already exists. Re-run with --force to merge contents or remove the file first.",
            file=sys.stderr,
        )
        return 1

    legacy_lines = _read_lines(legacy_path)
    primary_lines: list[str] = []
    if primary_path.exists():
        primary_lines = _read_lines(primary_path)

    merged_lines = _merge_unique_lines(primary_lines, legacy_lines)
    merged_text = "\n".join(merged_lines) + ("\n" if merged_lines else "")

    if dry_run:
        action = "would overwrite" if primary_path.exists() else "would write"
        print(f"dry-run: {action} {primary_path} with merged denylist and {'retain' if keep_legacy else 'remove'} {LEGACY_FILENAME}")
        if keep_legacy:
            print(f"dry-run: would also leave {legacy_path} in place for manual cleanup")
        else:
            print(f"dry-run: would delete legacy file {legacy_path}")
        return 0

    primary_path.write_text(merged_text, encoding="utf-8")
    if keep_legacy:
        print(f"migrated: wrote {PRIMARY_FILENAME} (legacy file retained for review)")
    else:
        legacy_path.unlink()
        print(f"migrated: wrote {PRIMARY_FILENAME} and removed {LEGACY_FILENAME}")

    print(
        "tip: keeping the denylist current avoids multi-gigabyte sanitized workspaces and speeds up Docker runs."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rename .codexignore to .projectsanitize with optional merging")
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project directory containing the sanitizer file (default: current directory)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show planned actions without writing changes")
    parser.add_argument("--force", action="store_true", help="Merge into an existing .projectsanitize when present")
    parser.add_argument(
        "--keep-legacy",
        action="store_true",
        help="Keep the legacy .codexignore after migrating (default removes it)",
    )
    args = parser.parse_args(argv)
    return migrate(Path(args.path), dry_run=args.dry_run, force=args.force, keep_legacy=args.keep_legacy)


if __name__ == "__main__":
    raise SystemExit(main())
