#!/usr/bin/env python3
"""Run Codex CLI against a checklist-style plan until all todos are complete."""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

import re


HEADING_RE = re.compile(r"^\s*(#{1,6})\s+(.*)$")
CHECKBOX_RE = re.compile(r"^\s*-\s*\[( |x|X)\]\s+(.*)$")


def parse_plan(plan_path: Path) -> List[Dict[str, object]]:
    sections: List[Dict[str, object]] = []
    current: Optional[Dict[str, object]] = None
    for raw_line in plan_path.read_text(encoding="utf-8").splitlines():
        heading_match = HEADING_RE.match(raw_line)
        if heading_match:
            if current:
                sections.append(current)
            current = {"title": heading_match.group(2).strip(), "tasks": []}
            continue
        if not current:
            continue
        checkbox_match = CHECKBOX_RE.match(raw_line)
        if checkbox_match:
            status_char = checkbox_match.group(1).lower()
            task_text = checkbox_match.group(2).strip()
            current["tasks"].append({"done": status_char == "x", "text": task_text})
    if current:
        sections.append(current)
    return sections


def first_incomplete(sections: List[Dict[str, object]]) -> Optional[Dict[str, object]]:
    for section in sections:
        if any(not task["done"] for task in section["tasks"]):
            return section
    return None


def build_prompt(plan_reference: str, section: Dict[str, object], attempt: int) -> str:
    todo_lines = "\n".join(f"- [ ] {task['text']}" for task in section["tasks"] if not task["done"])
    attempt_note = (
        "This is attempt number %d; please note any blockers explicitly if you cannot finish.\n"
        % attempt
        if attempt > 1
        else ""
    )
    return (
        f"You are collaborating on a workplan defined in {plan_reference}.\n"
        f"Current section: {section['title']}\n\n"
        f"Outstanding checklist items:\n{todo_lines}\n\n"
        "Execution rules:\n"
        "1. Make the repository changes (code, tests, docs, config) required to satisfy these items—editing the plan alone never counts.\n"
        f"2. Update {plan_reference} only after the work is complete, marking finished checkboxes as '- [x]' and adding a brief note about what changed.\n"
        "3. Run all relevant tests or linters and report their results in your reply.\n"
        "4. If a task cannot be finished, explain the blocker and leave its checkbox unchecked.\n"
        "5. Respond with three labelled sections: CHANGES (files touched and highlights), TESTS (commands + outcomes), NEXT (follow-ups or blockers).\n"
        f"{attempt_note}Focus only on this section before exiting."
    )


def ensure_completion(sections: List[Dict[str, object]], title: str) -> bool:
    for section in sections:
        if section["title"] == title:
            return all(task["done"] for task in section["tasks"])
    return True


def run_codex(command: List[str], prompt: str) -> int:
    result = subprocess.run(
        command,
        input=prompt,
        text=True,
        check=False,
    )
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Codex CLI against the phase checklist")
    parser.add_argument("--plan", default="docs/gitlab-project-cache.md", type=Path, help="Path to the plan markdown file")
    parser.add_argument("--codex", default="codex", help="Codex CLI executable name or path")
    parser.add_argument("--cd", default=".", type=Path, help="Working directory passed to codex exec")
    parser.add_argument("--max-attempts", default=3, type=int, help="Maximum Codex invocations per phase")
    args = parser.parse_args()

    plan_path: Path = args.plan.resolve()
    if not plan_path.exists():
        print(f"Plan file not found: {plan_path}", file=sys.stderr)
        return 1

    codex_cmd: List[str] = [args.codex, "exec", "--cd", str(args.cd.resolve()), "--skip-git-repo-check", "--yolo", "-"]

    while True:
        sections = parse_plan(plan_path)
        target = first_incomplete(sections)
        if not target:
            print("All checklist items are already complete.")
            return 0
        title = str(target["title"])
        print(f"Working on {title}")
        success = False
        for attempt in range(1, args.max_attempts + 1):
            try:
                plan_ref_path = plan_path.relative_to(Path.cwd())
            except ValueError:
                plan_ref_path = plan_path
            prompt = build_prompt(str(plan_ref_path), target, attempt)
            exit_code = run_codex(codex_cmd, prompt)
            if exit_code != 0:
                print(f"Codex exited with {exit_code}; aborting.", file=sys.stderr)
                return exit_code
            sections = parse_plan(plan_path)
            if ensure_completion(sections, title):
                print(f"Completed {title}")
                success = True
                break
            print(f"Phase still has open todos after attempt {attempt}; retrying.")
            target = next((section for section in sections if section["title"] == title), target)
        if not success:
            print(f"Reached {args.max_attempts} attempts without finishing {title}.", file=sys.stderr)
            return 1


if __name__ == "__main__":
    sys.exit(main())
