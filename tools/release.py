#!/usr/bin/env python3
"""Release automation utility: bump version, seed changelog, and optional git tag."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
INIT_FILE = ROOT / "conductor" / "__init__.py"
CHANGELOG = ROOT / "CHANGELOG.md"

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse_semver(version: str) -> tuple[int, int, int]:
    match = SEMVER_RE.match(version.strip())
    if not match:
        raise ValueError(f"Version is not strict semver: {version}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def bump_semver(version: str, part: str) -> str:
    major, minor, patch = parse_semver(version)
    if part == "major":
        major += 1
        minor = 0
        patch = 0
    elif part == "minor":
        minor += 1
        patch = 0
    elif part == "patch":
        patch += 1
    else:
        raise ValueError(f"Unknown bump part: {part}")
    return f"{major}.{minor}.{patch}"


def extract_pyproject_version(content: str) -> str:
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, flags=re.MULTILINE)
    if not match:
        raise RuntimeError("Could not find version in pyproject.toml")
    return match.group(1)


def extract_init_version(content: str) -> str:
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', content, flags=re.MULTILINE)
    if not match:
        raise RuntimeError("Could not find __version__ in conductor/__init__.py")
    return match.group(1)


def replace_pyproject_version(content: str, new_version: str) -> str:
    return re.sub(
        r'(^version\s*=\s*")[^"]+(")',
        rf"\g<1>{new_version}\2",
        content,
        flags=re.MULTILINE,
    )


def replace_init_version(content: str, new_version: str) -> str:
    return re.sub(
        r'(^__version__\s*=\s*")[^"]+(")',
        rf"\g<1>{new_version}\2",
        content,
        flags=re.MULTILINE,
    )


def ensure_changelog_heading(content: str, version: str, release_date: str) -> str:
    heading = f"## [{version}] - {release_date}"
    if heading in content:
        return content
    marker = "## [Unreleased]"
    insertion = f"{marker}\n\n{heading}\n\n### Added\n- TBD\n"
    if marker in content:
        return content.replace(marker, insertion, 1)
    return content.rstrip() + f"\n\n{heading}\n\n### Added\n- TBD\n"


def _write(path: Path, content: str) -> None:
    path.write_text(content)


def _prepare_release(part: str, create_tag: bool, dry_run: bool) -> int:
    pyproject_content = PYPROJECT.read_text()
    init_content = INIT_FILE.read_text()
    changelog_content = CHANGELOG.read_text() if CHANGELOG.exists() else "# Changelog\n\n## [Unreleased]\n"

    current_py = extract_pyproject_version(pyproject_content)
    current_init = extract_init_version(init_content)
    if current_py != current_init:
        print(f"ERROR: version mismatch pyproject={current_py}, init={current_init}", file=sys.stderr)
        return 1

    next_version = bump_semver(current_py, part)
    today = dt.date.today().isoformat()

    updated_pyproject = replace_pyproject_version(pyproject_content, next_version)
    updated_init = replace_init_version(init_content, next_version)
    updated_changelog = ensure_changelog_heading(changelog_content, next_version, today)

    if not dry_run:
        _write(PYPROJECT, updated_pyproject)
        _write(INIT_FILE, updated_init)
        _write(CHANGELOG, updated_changelog)

    print(f"current_version={current_py}")
    print(f"next_version={next_version}")
    print(f"tag=v{next_version}")
    print("")
    print("Next commands:")
    print("  git add pyproject.toml conductor/__init__.py CHANGELOG.md")
    print(f"  git commit -m \"chore(release): v{next_version}\"")
    print(f"  git tag -a v{next_version} -m \"release v{next_version}\"")

    if create_tag and not dry_run:
        subprocess.run(
            ["git", "tag", "-a", f"v{next_version}", "-m", f"release v{next_version}"],
            cwd=str(ROOT),
            check=True,
        )
        print(f"created_tag=v{next_version}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Release automation utility")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prepare = sub.add_parser("prepare", help="Bump version and seed changelog")
    p_prepare.add_argument("--part", choices=["major", "minor", "patch"], default="patch")
    p_prepare.add_argument("--tag", action="store_true", help="Create local annotated git tag after bump")
    p_prepare.add_argument("--dry-run", action="store_true", help="Preview changes without writing files")

    args = parser.parse_args()
    if args.command == "prepare":
        return _prepare_release(part=args.part, create_tag=args.tag, dry_run=args.dry_run)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
