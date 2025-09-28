#!/usr/bin/env python3
"""Launch Codex runs sequentially to execute the UI/UX improvement plan."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional, Tuple

DEFAULT_PROMPT_PATH = Path("prompts/ui_ux_next_phase_prompt.md")
DEFAULT_PLAN_PATH = Path("ui-ux-improvement-plan.md")
# Defaults align with Codex CLI docs (rust-v0.42.0) for headless runs.
DEFAULT_EXTRA_FLAGS = (
    "--skip-git-repo-check",
    "--dangerously-bypass-approvals-and-sandbox",
)


PhaseMatch = Optional[Tuple[str, str]]


def parse_next_phase(plan_text: str) -> PhaseMatch:
    pattern = re.compile(r"^## (Phase[^\n]+)\n(.*?)(?=\n## |\Z)", re.MULTILINE | re.DOTALL)
    for match in pattern.finditer(plan_text):
        body = match.group(2)
        if "[ ]" in body:
            title = match.group(1).strip()
            return title, body.strip()
    return None


def load_prompt(prompt_path: Path) -> str:
    try:
        return prompt_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"error: prompt file not found at {prompt_path}") from exc


def run_codex(prompt: str, codex_bin: str, workdir: Path, extra_flags: Iterable[str]) -> int:
    cmd = [codex_bin, "exec", "--cd", str(workdir)]
    cmd.extend(extra_flags)
    cmd.append("-")
    process = subprocess.run(cmd, input=prompt, check=False, text=True)
    return process.returncode


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt-path", type=Path, default=DEFAULT_PROMPT_PATH)
    parser.add_argument("--plan-path", type=Path, default=DEFAULT_PLAN_PATH)
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--workdir", type=Path, default=Path("."))
    parser.add_argument("--max-iterations", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true", help="show the next phase without launching Codex")
    parser.add_argument("--flag", dest="extra_flags", action="append", default=[], help="append an extra flag for each Codex exec run")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    prompt_text = load_prompt(args.prompt_path)

    try:
        plan_text = args.plan_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"error: plan file not found at {args.plan_path}") from exc

    iteration = 0
    while iteration < args.max_iterations:
        phase_match = parse_next_phase(plan_text)
        if not phase_match:
            if iteration == 0:
                print("All UI/UX plan phases are already complete.")
            else:
                print("All UI/UX plan phases are now complete.")
            return 0

        phase_title, phase_body = phase_match
        print(f"[phase-runner] Next phase: {phase_title}")
        if args.verbose:
            print("[phase-runner] Outstanding checklist items:\n")
            print(phase_body)
            print()

        if args.dry_run:
            return 0

        extra_flags = list(DEFAULT_EXTRA_FLAGS)
        extra_flags.extend(args.extra_flags)
        code = run_codex(prompt_text, args.codex_bin, args.workdir.resolve(), extra_flags)
        if code != 0:
            print(f"[phase-runner] Codex exited with status {code}")
            return code

        iteration += 1
        try:
            plan_text = args.plan_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise SystemExit(f"error: plan file missing after Codex run ({args.plan_path})") from exc

    print(
        "[phase-runner] Reached iteration limit without completing all phases; "
        "rerun after reviewing remaining checklist items."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
