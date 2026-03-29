#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from pathlib import Path

from _project_paths import find_repo_root
from _safe_files import is_safe_regular_file
from risk_classifier import suggest_risk
from validate_skills import configure_utf8_output, parse_frontmatter


FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
SAFE_BLOCKLIST_PATTERN = re.compile(
    r"\b(?:"
    r"create|write|overwrite|append|modify|update|delete|remove|deploy|publish|"
    r"push|commit|merge|install|token|secret|password|oauth|api[_ -]?key|"
    r"POST|PUT|PATCH|DELETE"
    r")\b",
    re.IGNORECASE,
)
STRONG_CRITICAL_REASONS = {
    "curl pipes into a shell",
    "wget pipes into a shell",
    "PowerShell invoke-expression",
    "destructive filesystem delete",
    "git mutation",
    "package publication",
    "deployment or infrastructure mutation",
}
SAFE_ALLOWED_REASONS = {
    "non-mutating command example",
    "contains fenced examples",
    "read-only or diagnostic language",
    "technical or integration language",
}
EXPLICIT_OFFENSIVE_REASON = "explicit offensive disclaimer"


def strip_frontmatter(content: str) -> tuple[str, str] | None:
    match = FRONTMATTER_PATTERN.search(content)
    if not match:
        return None
    return match.group(1), content[match.end():]


def replace_risk_value(content: str, new_risk: str) -> str:
    frontmatter = strip_frontmatter(content)
    if frontmatter is None:
        return content

    frontmatter_text, body = frontmatter
    lines = frontmatter_text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("risk:"):
            indent = line[: len(line) - len(line.lstrip())]
            lines[index] = f"{indent}risk: {new_risk}"
            break
    else:
        return content

    updated_frontmatter = "\n".join(lines)
    return f"---\n{updated_frontmatter}\n---{body}"


def choose_synced_risk(content: str, metadata: dict[str, object] | None) -> tuple[str, tuple[str, ...]] | None:
    if not metadata or metadata.get("risk") != "unknown":
        return None

    suggestion = suggest_risk(content, metadata)
    reasons = tuple(suggestion.reasons)
    reason_set = set(reasons)

    if suggestion.risk == "offensive":
        if EXPLICIT_OFFENSIVE_REASON in reason_set:
            return "offensive", reasons
        return None

    if suggestion.risk == "critical":
        if reason_set & STRONG_CRITICAL_REASONS:
            return "critical", reasons
        return None

    if suggestion.risk == "safe":
        if not reason_set:
            return None
        if not reason_set.issubset(SAFE_ALLOWED_REASONS):
            return None
        if SAFE_BLOCKLIST_PATTERN.search(content):
            return None
        return "safe", reasons

    return None


def update_skill_file(skill_path: Path) -> tuple[bool, str | None, tuple[str, ...]]:
    if not is_safe_regular_file(skill_path):
        return False, None, ()

    content = skill_path.read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(content, skill_path.as_posix())
    decision = choose_synced_risk(content, metadata)
    if decision is None:
        return False, None, ()

    new_risk, reasons = decision
    updated_content = replace_risk_value(content, new_risk)
    if updated_content == content:
        return False, None, ()

    skill_path.write_text(updated_content, encoding="utf-8")
    return True, new_risk, reasons


def iter_skill_files(skills_dir: Path):
    for root, dirs, files in os.walk(skills_dir):
        dirs[:] = [directory for directory in dirs if not directory.startswith(".")]
        if "SKILL.md" in files:
            yield Path(root) / "SKILL.md"


def main() -> int:
    configure_utf8_output()

    parser = argparse.ArgumentParser(
        description="Conservatively sync legacy risk: unknown labels to concrete values.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing files.")
    args = parser.parse_args()

    repo_root = find_repo_root(__file__)
    skills_dir = repo_root / "skills"

    updated_count = 0
    by_risk: Counter[str] = Counter()

    for skill_path in iter_skill_files(skills_dir):
        content = skill_path.read_text(encoding="utf-8")
        metadata, _ = parse_frontmatter(content, skill_path.as_posix())
        decision = choose_synced_risk(content, metadata)
        if decision is None:
            continue

        new_risk, reasons = decision
        rel_path = skill_path.relative_to(repo_root)

        if args.dry_run:
            print(f"SYNC {rel_path} [risk={new_risk}; reasons={', '.join(reasons[:3])}]")
            updated_count += 1
            by_risk[new_risk] += 1
            continue

        changed, applied_risk, applied_reasons = update_skill_file(skill_path)
        if changed and applied_risk is not None:
            print(
                f"SYNC {rel_path} [risk={applied_risk}; reasons={', '.join(applied_reasons[:3])}]"
            )
            updated_count += 1
            by_risk[applied_risk] += 1

    print(f"\nUpdated: {updated_count}")
    if updated_count:
        print(f"By risk: {dict(sorted(by_risk.items()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
