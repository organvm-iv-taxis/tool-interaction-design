"""Layer 3: Product Extractor — export process, mine patterns, generate reports."""

from __future__ import annotations

import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import yaml

from .constants import (
    EXPORTS_DIR,
    GENERATED_DIR,
    PHASES,
    SESSIONS_DIR,
    TEMPLATES_DIR,
)
from .governance import GovernanceRuntime


class ProductExtractor:
    """Layer 3: Export process, mine patterns, generate audit reports."""

    def __init__(self, governance: GovernanceRuntime) -> None:
        self.governance = governance

    def export_process_kit(self, output_dir: Optional[Path] = None) -> None:
        """Export templates, CI artifacts, and a standalone conductor as a reusable kit."""
        output = output_dir or EXPORTS_DIR / "process-kit"
        output.mkdir(parents=True, exist_ok=True)

        print(f"\n  Exporting Process Kit -> {output}")
        print("  " + "=" * 50)

        # Copy templates
        templates_out = output / "templates"
        templates_out.mkdir(exist_ok=True)
        for f in TEMPLATES_DIR.glob("*.md"):
            shutil.copy2(f, templates_out / f.name)
            print(f"  + templates/{f.name}")

        # Copy generated CI artifacts if they exist
        if GENERATED_DIR.exists():
            for f in GENERATED_DIR.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(GENERATED_DIR)
                    dest = output / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dest)
                    print(f"  + {rel}")

        # Generate CLAUDE.md
        claude_md = output / "CLAUDE.md"
        claude_md.write_text("""# CLAUDE.md -- Process Kit Template

## Session Workflow

This project uses the FRAME/SHAPE/BUILD/PROVE lifecycle:

1. **FRAME** -- Define scope, research the problem, create spec.md
2. **SHAPE** -- Design the approach, create plan.md, branch
3. **BUILD** -- Implement step by step, test continuously
4. **PROVE** -- Lint, security scan, create PR, review

## Templates

- `templates/spec.md` -- FRAME output
- `templates/plan.md` -- SHAPE output
- `templates/status.md` -- Session close log

## Commands

```bash
python3 -m conductor session start --organ <ORGAN> --repo <REPO> --scope "Description"
python3 -m conductor session phase shape
python3 -m conductor session phase build
python3 -m conductor session phase prove
python3 -m conductor session close
```
""")
        print(f"  + CLAUDE.md")

        # Generate README
        readme = output / "README.md"
        readme.write_text("""# Process Kit

A session-based development workflow built on the FRAME/SHAPE/BUILD/PROVE lifecycle.

## What's Included

- **Templates**: spec.md, plan.md, status.md -- scaffolded per session
- **CI Workflows**: lifecycle validation, WIP limit checking
- **PR Template**: governance gates checklist
- **Issue Form**: lifecycle-aware feature requests
- **CLAUDE.md**: AI assistant configuration

## Quick Start

1. Copy this directory into your project
2. Install: `pip install pyyaml`
3. Run: `python3 -m conductor session start --organ III --repo my-repo --scope "My feature"`

## The Lifecycle

```
FRAME  ->  SHAPE  ->  BUILD  ->  PROVE  ->  DONE
  ^          |                    |
  +----------+ (reshape)         +-- (fail -> back to BUILD)
```

Each phase activates specific tool clusters and AI roles.
Built by the conductor operating system.
""")
        print(f"  + README.md")

        # Session log schema (P5.2)
        schema = output / "session-log-schema.yaml"
        schema.write_text("""# Session Log Schema v1.0
# Each session close generates a YAML file conforming to this schema.

type: object
required: [session_id, organ, repo, scope, duration_minutes, phases, result, timestamp]
properties:
  session_id:
    type: string
    pattern: "^\\\\d{4}-\\\\d{2}-\\\\d{2}-[A-Z]+-.*$"
  organ:
    type: string
    enum: [ORGAN-I, ORGAN-II, ORGAN-III, ORGAN-IV, ORGAN-V, ORGAN-VI, ORGAN-VII, META-ORGANVM]
  repo:
    type: string
  scope:
    type: string
  duration_minutes:
    type: integer
    minimum: 0
  phases:
    type: object
    properties:
      FRAME: { $ref: "#/$defs/phase_entry" }
      SHAPE: { $ref: "#/$defs/phase_entry" }
      BUILD: { $ref: "#/$defs/phase_entry" }
      PROVE: { $ref: "#/$defs/phase_entry" }
  warnings:
    type: array
    items: { type: string }
  result:
    type: string
    enum: [SHIPPED, CLOSED, IN_PROGRESS]
  timestamp:
    type: string
    format: date-time

$defs:
  phase_entry:
    type: object
    required: [duration, tools_used, commits, visits]
    properties:
      duration: { type: integer }
      tools_used: { type: array, items: { type: string } }
      commits: { type: integer }
      visits: { type: integer }
""")
        print(f"  + session-log-schema.yaml")

        total = sum(1 for _ in output.rglob("*") if _.is_file())
        print(f"\n  Exported {total} files to {output}")
        print()

    def mine_patterns(self, export_essay: bool = False) -> None:
        """Mine session logs for recurring patterns."""
        print("\n  Pattern Mining")
        print("  " + "=" * 50)

        session_logs = list(SESSIONS_DIR.glob("*/session-log.yaml"))
        if not session_logs:
            print("  No session logs found. Complete some sessions first.")
            print()
            return

        total_sessions = len(session_logs)
        phase_durations: dict[str, list[int]] = defaultdict(list)
        tool_frequency: Counter = Counter()
        warning_types: Counter = Counter()
        results: Counter = Counter()
        organs_used: Counter = Counter()

        for log_path in session_logs:
            log = yaml.safe_load(log_path.read_text())

            results[log.get("result", "UNKNOWN")] += 1
            organs_used[log.get("organ", "UNKNOWN")] += 1

            for phase_name, phase_data in log.get("phases", {}).items():
                if isinstance(phase_data, dict):
                    phase_durations[phase_name].append(phase_data.get("duration", 0))
                    for tool in phase_data.get("tools_used", []):
                        tool_frequency[tool] += 1

            for w in log.get("warnings", []):
                if "during FRAME" in w:
                    warning_types["phase_violation_FRAME"] += 1
                elif "during SHAPE" in w:
                    warning_types["phase_violation_SHAPE"] += 1
                elif "during BUILD" in w:
                    warning_types["phase_violation_BUILD"] += 1
                else:
                    warning_types["other"] += 1

        print(f"\n  Sessions analyzed: {total_sessions}")
        print(f"  Results: {dict(results)}")
        print(f"  Organs: {dict(organs_used)}")

        print(f"\n  Phase Duration Averages:")
        for phase in PHASES:
            durs = phase_durations.get(phase, [])
            if durs:
                avg = sum(durs) / len(durs)
                print(f"    {phase:<8} avg={avg:.0f}m  min={min(durs)}m  max={max(durs)}m  n={len(durs)}")

        if tool_frequency:
            print(f"\n  Top 10 Tools:")
            for tool, count in tool_frequency.most_common(10):
                print(f"    {tool:<35} {count}x")

        if warning_types:
            print(f"\n  Warning Patterns:")
            for wtype, count in warning_types.most_common():
                print(f"    {wtype:<35} {count}x")

        # Named patterns
        patterns = []
        avg_frame = sum(phase_durations.get("FRAME", [0])) / max(len(phase_durations.get("FRAME", [1])), 1)
        avg_build = sum(phase_durations.get("BUILD", [0])) / max(len(phase_durations.get("BUILD", [1])), 1)

        if avg_frame > 20:
            patterns.append(("DEEP_RESEARCH", f"FRAME phase averages {avg_frame:.0f}m -- research-heavy workflow"))
        elif avg_frame < 5 and total_sessions > 3:
            patterns.append(("QUICK_FRAME", f"FRAME phase averages {avg_frame:.0f}m -- consider more upfront research"))

        if avg_build > 60:
            patterns.append(("MARATHON_BUILD", f"BUILD phase averages {avg_build:.0f}m -- consider smaller scopes"))

        if warning_types.get("phase_violation_FRAME", 0) > total_sessions * 0.3:
            patterns.append(("EAGER_CODER", "Frequent code tool use during FRAME -- slow down, research first"))

        if patterns:
            print(f"\n  Detected Patterns:")
            for name, desc in patterns:
                print(f"    [{name}] {desc}")

        shipped = results.get("SHIPPED", 0)
        if total_sessions > 0:
            ship_rate = shipped / total_sessions * 100
            print(f"\n  Ship rate: {shipped}/{total_sessions} ({ship_rate:.0f}%)")

        # Export essay draft (P5.4)
        if export_essay and total_sessions >= 3:
            self._export_pattern_essay(total_sessions, results, phase_durations, patterns, tool_frequency)

        print()

    def _export_pattern_essay(
        self,
        total_sessions: int,
        results: Counter,
        phase_durations: dict[str, list[int]],
        patterns: list[tuple[str, str]],
        tool_frequency: Counter,
    ) -> None:
        """Generate a draft essay from pattern data."""
        EXPORTS_DIR.mkdir(exist_ok=True)
        essay_path = EXPORTS_DIR / "pattern-essay-draft.md"

        shipped = results.get("SHIPPED", 0)
        ship_rate = shipped / total_sessions * 100 if total_sessions else 0

        lines = [
            f"# What {total_sessions} Conductor Sessions Taught Me\n",
            f"*Draft generated from session data. Edit before publishing.*\n",
            f"\n## The Numbers\n",
            f"- **{total_sessions}** sessions completed",
            f"- **{ship_rate:.0f}%** ship rate ({shipped} shipped, {results.get('CLOSED', 0)} closed without shipping)",
        ]

        for phase in PHASES:
            durs = phase_durations.get(phase, [])
            if durs:
                avg = sum(durs) / len(durs)
                lines.append(f"- **{phase}**: avg {avg:.0f}m per session")

        if patterns:
            lines.append(f"\n## Patterns Observed\n")
            for name, desc in patterns:
                lines.append(f"### {name}\n")
                lines.append(f"{desc}\n")

        if tool_frequency:
            lines.append(f"\n## Most-Used Tools\n")
            for tool, count in tool_frequency.most_common(5):
                lines.append(f"- **{tool}**: {count} uses")

        lines.append(f"\n---\n*Generated by conductor pattern mining.*\n")

        essay_path.write_text("\n".join(lines))
        print(f"\n  Essay draft exported: {essay_path}")

    def export_audit_report(self, organ: Optional[str] = None) -> None:
        """Generate a structured audit report."""
        print(f"\n  Generating Audit Report: {organ or 'FULL SYSTEM'}")
        print("  " + "=" * 50)

        self.governance.audit(organ)

        session_logs = list(SESSIONS_DIR.glob("*/session-log.yaml"))
        if session_logs:
            print(f"\n  Session Metrics ({len(session_logs)} sessions):")
            total_minutes = 0
            for log_path in session_logs:
                log = yaml.safe_load(log_path.read_text())
                total_minutes += log.get("duration_minutes", 0)
            print(f"    Total session time: {total_minutes} minutes ({total_minutes / 60:.1f} hours)")
            print(f"    Average session: {total_minutes / len(session_logs):.0f} minutes")
        print()
