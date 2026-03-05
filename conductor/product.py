"""Layer 3: Product Extractor — export process, mine patterns, generate reports."""

from __future__ import annotations

import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from .constants import (
    ConductorError,
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

    def export_process_kit(self, output_dir: Optional[Path] = None, force: bool = False) -> None:
        """Export templates, CI artifacts, and a standalone conductor as a reusable kit."""
        output = output_dir or EXPORTS_DIR / "process-kit"

        if output.exists() and not output.is_dir():
            raise ConductorError(f"Output path exists and is not a directory: {output}")

        if output.is_dir() and any(output.iterdir()) and not force:
            raise ConductorError(
                f"Output directory already exists and is not empty: {output}\n"
                f"  Use --force to overwrite."
            )

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
        frame_durs = phase_durations.get("FRAME", [])
        build_durs = phase_durations.get("BUILD", [])
        avg_frame = sum(frame_durs) / len(frame_durs) if frame_durs else 0
        avg_build = sum(build_durs) / len(build_durs) if build_durs else 0

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

    def export_gemini_extension(self, output_dir: Optional[Path] = None, force: bool = False) -> None:
        """Export the entire Conductor OS as a standalone Gemini CLI Extension."""
        output = output_dir or EXPORTS_DIR / "conductor-extension"

        if output.exists() and not output.is_dir():
            raise ConductorError(f"Output path exists and is not a directory: {output}")

        if output.is_dir() and any(output.iterdir()) and not force:
            raise ConductorError(
                f"Output directory already exists and is not empty: {output}\n"
                f"  Use --force to overwrite."
            )

        output.mkdir(parents=True, exist_ok=True)

        print(f"\n  Forging Gemini Extension -> {output}")
        print("  " + "=" * 50)

        # 1. Generate Manifest
        manifest = {
            "name": "conductor-os",
            "version": "1.0.0",
            "description": "The AI-Conductor's Operating System. Provides JIT Workflow Compilation, Governance, and Orchestration.",
            "contextFileName": "GEMINI.md",
            "mcpServers": {
                "conductor-os": {
                    "command": "python3",
                    "args": ["${extensionPath}/mcp_server.py"]
                }
            }
        }
        (output / "gemini-extension.json").write_text(json.dumps(manifest, indent=2))
        print(f"  + gemini-extension.json")

        # 2. Generate System Prompt (GEMINI.md)
        gemini_md = output / "GEMINI.md"
        gemini_md.write_text("""# Conductor OS Extension

You are augmented with the Conductor Operating System. This extension provides you with 'God Mode' orchestration capabilities.

## Core Capabilities
- **Routing:** You can use `conductor_route_to` to find the safest path between tool capabilities.
- **Synthesis:** If you encounter a complex multi-step problem, use `conductor_compose_mission` to automatically generate a stateful execution plan.
- **Execution:** Execute synthesized missions step-by-step using `conductor_workflow_step`.

## Mandate
You must prioritize institutional governance. Before modifying repositories, consult the `conductor_patchbay` to ensure no WIP limits are violated. If a mission path is degraded, the compiler will inject a `validation_checkpoint`—you must respect these checkpoints and run the suggested validation tools before proceeding.
""")
        print(f"  + GEMINI.md")

        # 3. Copy Core Engine Files
        core_files = [
            "mcp_server.py",
            "router.py",
            "ontology.yaml",
            "routing-matrix.yaml",
            "workflow-dsl.yaml"
        ]
        
        from .constants import BASE
        for fname in core_files:
            src = BASE / fname
            if src.exists():
                shutil.copy2(src, output / fname)
                print(f"  + {fname}")

        # 4. Copy Conductor Package
        conductor_pkg = output / "conductor"
        if conductor_pkg.exists():
            shutil.rmtree(conductor_pkg)
        shutil.copytree(BASE / "conductor", conductor_pkg, ignore=shutil.ignore_patterns("__pycache__"))
        print(f"  + conductor/ (Python core)")

        # 5. Provide Install Script
        install_sh = output / "install.sh"
        install_sh.write_text("""#!/bin/bash
echo "Installing Conductor OS dependencies..."
python3 -m pip install pyyaml jsonschema
echo "Dependencies installed. You can now enable the extension in Gemini CLI."
""")
        install_sh.chmod(0o755)
        print(f"  + install.sh")

        print(f"\n  Forge complete. To deploy:")
        print(f"  1. cd {output}")
        print(f"  2. ./install.sh")
        print(f"  3. gemini extensions install .\n")

    def export_fleet_dashboard(self, output_dir: Optional[Path] = None) -> None:
        """Generate a static HTML dashboard aggregating all telemetry and WIP states."""
        output = output_dir or EXPORTS_DIR / "fleet-dashboard"
        output.mkdir(parents=True, exist_ok=True)
        
        from .patchbay import Patchbay
        from .observability import get_metrics, compute_trend_report
        pb = Patchbay(ontology=None, engine=None)
        
        # We must sync the queue so the registry is up to date
        pb.briefing()
        
        pulse = pb._pulse_section()
        stats = pb._stats_section()
        queue = pb._queue_section()
        trends = compute_trend_report()
        obs = get_metrics()

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ORGANVM Fleet Admiral Dashboard</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #0d1117; color: #e2e8f0; margin: 0; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1, h2, h3 {{ color: #63b3ed; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 20px; }}
        .card {{ background: #1a202c; border: 1px solid #2d3748; border-radius: 8px; padding: 20px; }}
        .stat {{ font-size: 2em; font-weight: bold; color: #48bb78; }}
        .stat.warning {{ color: #ecc94b; }}
        .stat.danger {{ color: #f56565; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #2d3748; }}
        th {{ color: #a0aec0; font-weight: normal; }}
        .tag {{ display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 0.8em; margin-right: 4px; }}
        .tag-critical {{ background: #742a2a; color: #fed7d7; }}
        .tag-warn {{ background: #744210; color: #fef08a; }}
        .tag-ok {{ background: #22543d; color: #c6f6d5; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>ORGANVM Fleet Admiral Dashboard</h1>
        <p>Generated: {datetime.now(timezone.utc).isoformat()}</p>
        
        <div class="grid">
            <div class="card">
                <h2>System Health</h2>
                <div class="stat {'danger' if trends['status'] == 'critical' else 'warning' if trends['status'] == 'warn' else 'ok'}">{trends['status'].upper()}</div>
                <p>Recent Failure Rate: {trends['recent']['failure_rate']*100:.1f}%</p>
                <p>Total Repos: {pulse['total_repos']}</p>
            </div>
            <div class="card">
                <h2>WIP Limits</h2>
                <div class="stat {'danger' if pulse['violations_count'] > 0 else 'ok'}">{pulse['violations_count']}</div>
                <p>Organs in Violation</p>
                <p>Total Candidate Repos: {pulse['total_candidate']}</p>
            </div>
            <div class="card">
                <h2>Delivery Metrics</h2>
                <div class="stat">{stats['ship_rate']}%</div>
                <p>Lifetime Ship Rate ({stats['shipped']}/{stats['total_sessions']} sessions)</p>
                <p>Current Streak: {stats['streak']}</p>
            </div>
        </div>

        <div class="card">
            <h2>Work Queue (Top 10)</h2>
            <table>
                <tr><th>ID</th><th>Priority</th><th>Organ</th><th>Description</th><th>Status</th><th>Owner</th></tr>"""
        
        for item in queue.get('items', []):
            p_class = "tag-critical" if item['priority'] == "CRITICAL" else "tag-warn" if item['priority'] == "HIGH" else "tag-ok"
            s_class = "tag-warn" if item['status'] == "CLAIMED" else "tag-ok" if item['status'] == "RESOLVED" else ""
            html += f"""
                <tr>
                    <td><code>{item['id']}</code></td>
                    <td><span class="tag {p_class}">{item['priority']}</span></td>
                    <td>{item['organ']}</td>
                    <td>{item['description']}</td>
                    <td><span class="tag {s_class}">{item['status']}</span></td>
                    <td>{item['owner'] or '-'}</td>
                </tr>"""

        html += """
            </table>
        </div>
        
        <div class="card">
            <h2>Organ Pulse</h2>
            <table>
                <tr><th>Organ</th><th>Total</th><th>Local</th><th>Candidate</th><th>Public Process</th><th>Graduated</th><th>Archived</th><th>Flags</th></tr>"""
                
        for key, o in sorted(pulse.get('organs', {}).items()):
            flags = ", ".join([f"<span class='tag tag-danger'>{f}</span>" if ">" in f else f"<span class='tag tag-warn'>{f}</span>" for f in o.get("flags", [])])
            html += f"""
                <tr>
                    <td><strong>{o['short']}</strong></td>
                    <td>{o['total']}</td>
                    <td>{o['local']}</td>
                    <td>{o['candidate']}</td>
                    <td>{o['public_process']}</td>
                    <td>{o['graduated']}</td>
                    <td>{o['archived']}</td>
                    <td>{flags}</td>
                </tr>"""

        html += """
            </table>
        </div>
    </div>
</body>
</html>"""
        
        index_file = output / "index.html"
        index_file.write_text(html)
        print(f"\n  Fleet Dashboard generated: {index_file}\n")

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
