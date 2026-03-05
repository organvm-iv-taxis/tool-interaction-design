"""CLI argument parser definition for conductor."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="conductor",
        description="The AI-Conductor's Operating System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # ----- Session commands -----
    p_session = sub.add_parser("session", help="Session lifecycle management")
    session_sub = p_session.add_subparsers(dest="session_command", required=True)

    p_start = session_sub.add_parser("start", help="Start a new session")
    p_start.add_argument("--organ", required=True, help="Organ key (e.g., III, META)")
    p_start.add_argument("--repo", required=True, help="Repository name")
    p_start.add_argument("--scope", required=True, help="Session scope description")
    p_start.add_argument("--no-branch", action="store_true", help="Skip git branch creation")

    p_phase = session_sub.add_parser("phase", help="Transition to next phase")
    p_phase.add_argument("target", help="Target phase (shape, build, prove, done)")

    session_sub.add_parser("status", help="Show current session status")
    session_sub.add_parser("close", help="Close session and generate log")

    p_log_tool = session_sub.add_parser("log-tool", help="Record a tool use")
    p_log_tool.add_argument("tool_name", help="Name of the tool used")

    # ----- Governance commands -----
    p_registry = sub.add_parser("registry", help="Registry operations")
    registry_sub = p_registry.add_subparsers(dest="registry_command", required=True)
    p_sync = registry_sub.add_parser("sync", help="Sync registry with GitHub")
    p_sync.add_argument("--fix", action="store_true", help="Auto-add missing repos")
    p_sync.add_argument("--dry-run", action="store_true", help="Show what --fix would do without writing")

    p_wip = sub.add_parser("wip", help="WIP limit management")
    wip_sub = p_wip.add_subparsers(dest="wip_command", required=True)
    wip_sub.add_parser("check", help="Show WIP status")
    p_promote = wip_sub.add_parser("promote", help="Promote repo with WIP enforcement")
    p_promote.add_argument("repo", help="Repository name")
    p_promote.add_argument("state", help="Target state (CANDIDATE, PUBLIC_PROCESS, etc.)")
    p_promote.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    p_auto_promote = wip_sub.add_parser("auto-promote", help="Auto-promote healthy repos while respecting WIP limits")
    p_auto_promote.add_argument(
        "--apply",
        action="store_true",
        help="Apply promotions (default is dry-run preview)",
    )
    p_auto_promote.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    p_enforce = sub.add_parser("enforce", help="Generate enforcement artifacts")
    enforce_sub = p_enforce.add_subparsers(dest="enforce_command", required=True)
    p_gen = enforce_sub.add_parser("generate", help="Generate rulesets and workflows")
    p_gen.add_argument("--dry-run", action="store_true", help="Show what would be generated")

    p_stale = sub.add_parser("stale", help="Find stale CANDIDATE repos")
    p_stale.add_argument("--days", type=int, default=30, help="Days threshold (default: 30)")

    p_audit = sub.add_parser("audit", help="Organ health audit")
    p_audit.add_argument("--organ", help="Organ key (default: full system)")
    p_audit.add_argument("--create-issues", action="store_true", help="File GitHub issues for findings")
    p_audit.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    # ----- Work Registry commands -----
    p_queue = sub.add_parser("queue", help="Work item registry management")
    queue_sub = p_queue.add_subparsers(dest="queue_command", required=True)
    p_q_claim = queue_sub.add_parser("claim", help="Claim a work item")
    p_q_claim.add_argument("item_id", help="Item ID to claim")
    p_q_claim.add_argument("--owner", help="Optional owner name (defaults to 'agent')")
    
    p_q_yield = queue_sub.add_parser("yield", help="Yield a claimed work item")
    p_q_yield.add_argument("item_id", help="Item ID to yield")
    
    p_q_resolve = queue_sub.add_parser("resolve", help="Mark a work item as resolved")
    p_q_resolve.add_argument("item_id", help="Item ID to resolve")

    p_auto = sub.add_parser("auto", help="Autonomous worker daemon")
    p_auto.add_argument("--daemon", action="store_true", help="Run in continuous loop")
    p_auto.add_argument("--interval", type=int, default=60, help="Check interval in seconds")
    p_auto.add_argument("--limit", type=int, default=1, help="Max tasks to perform")

    # ----- Product commands -----
    p_export = sub.add_parser("export", help="Export artifacts")
    export_sub = p_export.add_subparsers(dest="export_command", required=True)
    p_kit = export_sub.add_parser("process-kit", help="Export process kit")
    p_kit.add_argument("--output", type=Path, help="Output directory")
    p_kit.add_argument("--force", action="store_true", help="Overwrite existing output")
    p_ext = export_sub.add_parser("gemini-extension", help="Export Conductor OS as a Gemini CLI extension")
    p_ext.add_argument("--output", type=Path, help="Output directory")
    p_ext.add_argument("--force", action="store_true", help="Overwrite existing output")
    p_fleet = export_sub.add_parser("fleet-dashboard", help="Export HTML Fleet Admiral Dashboard")
    p_fleet.add_argument("--output", type=Path, help="Output directory")
    p_report = export_sub.add_parser("audit-report", help="Export audit report")
    p_report.add_argument("--organ", help="Organ key (default: full system)")

    p_retro = sub.add_parser("retro", help="Generate retrospective from session and observability data")
    p_retro.add_argument("--last", type=int, default=0, help="Analyze only the last N sessions (default: all)")
    p_retro.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    p_patterns = sub.add_parser("patterns", help="Mine session logs for patterns")
    p_patterns.add_argument("--export-essay", action="store_true", help="Export pattern essay draft")

    # ----- Router commands (inherited) -----
    p_route = sub.add_parser("route", help="Find routes between clusters")
    route_sub = p_route.add_subparsers(dest="route_command")
    p_route.add_argument("--from", dest="from_cluster")
    p_route.add_argument("--to", dest="to_cluster")
    p_route_sim = route_sub.add_parser("simulate", help="Simulate a routed handoff with repair/fallback behavior")
    p_route_sim.add_argument("--from", dest="from_cluster", required=True)
    p_route_sim.add_argument("--to", dest="to_cluster", required=True)
    p_route_sim.add_argument("--objective", required=True, help="Objective for the simulated handoff")
    p_route_sim.add_argument("--deadline-ms", type=int, default=5000, help="Deadline budget for simulation")
    p_route_sim.add_argument("--priority", choices=["low", "medium", "high", "critical"], default="high")
    p_route_sim.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    p_cap = sub.add_parser("capability", help="Find clusters by capability")
    p_cap.add_argument("cap", type=str)

    p_validate = sub.add_parser("validate", help="Validate a workflow DSL file")
    p_validate.add_argument("file", type=str)
    p_validate.add_argument("--strict", action="store_true", help="Treat warnings as validation failures")
    p_validate.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    p_compose = sub.add_parser("compose", help="Synthesize a JIT workflow mission")
    p_compose.add_argument("--goal", required=True, help="High-level goal description")
    p_compose.add_argument("--from", dest="from_cluster", required=True, help="Starting tool cluster")
    p_compose.add_argument("--to", dest="to_cluster", required=True, help="Target tool cluster")
    p_compose.add_argument("--session-id", help="Optional session ID")
    p_compose.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    p_workflow = sub.add_parser("workflow", help="Workflow DSL runtime commands")
    workflow_sub = p_workflow.add_subparsers(dest="workflow_command", required=True)
    workflow_sub.add_parser("list", help="List available workflow names")
    p_workflow_start = workflow_sub.add_parser("start", help="Start workflow execution state")
    p_workflow_start.add_argument("--name", required=True, help="Workflow name from workflow-dsl.yaml")
    p_workflow_start.add_argument("--session-id", help="Optional session id (default: active session or generated)")
    p_workflow_start.add_argument("--input-json", help="Optional JSON payload for workflow input")
    p_workflow_start.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_workflow_status = workflow_sub.add_parser("status", help="Show workflow execution status")
    p_workflow_status.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_workflow_step = workflow_sub.add_parser("step", help="Execute one workflow step")
    p_workflow_step.add_argument("--name", required=True, help="Step name to execute")
    p_workflow_step.add_argument("--output-json", help="Optional JSON payload for step output")
    p_workflow_step.add_argument(
        "--checkpoint-action",
        choices=["approve", "modify", "abort"],
        help="Checkpoint decision when the step is gated",
    )
    p_workflow_step.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_workflow_resume = workflow_sub.add_parser("resume", help="Resume a failed or paused workflow")
    p_workflow_resume.add_argument("--from", dest="from_step", help="Step name to rewind to and re-execute from")
    p_workflow_resume.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    workflow_sub.add_parser("clear", help="Clear persisted workflow execution state")

    p_doctor = sub.add_parser("doctor", help="Run conductor integrity diagnostics")
    p_doctor.add_argument("--workflow", type=Path, default=Path("workflow-dsl.yaml"), help="Workflow file to validate")
    p_doctor.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_doctor.add_argument("--strict", action="store_true", help="Exit non-zero on any failing check")
    p_doctor.add_argument("--apply", action="store_true", help="Apply available schema autofixes before reporting")
    p_doctor.add_argument("--tools", action="store_true", help="Check which ontology tools are actually available")

    p_plugins = sub.add_parser("plugins", help="Plugin diagnostics")
    plugin_sub = p_plugins.add_subparsers(dest="plugins_command", required=True)
    p_plugins_doctor = plugin_sub.add_parser("doctor", help="Validate plugin manifests and provider loading")
    p_plugins_doctor.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_plugins_doctor.add_argument("--strict", action="store_true", help="Fail on warnings in addition to errors")

    p_policy = sub.add_parser("policy", help="Policy analysis commands")
    policy_sub = p_policy.add_subparsers(dest="policy_command", required=True)
    p_policy_simulate = policy_sub.add_parser("simulate", help="Simulate policy limits against registry state")
    p_policy_simulate.add_argument("--bundle", help="Policy bundle name to simulate (default resolves from env/config)")
    p_policy_simulate.add_argument("--organ", help="Optional organ filter (e.g., III, META)")
    p_policy_simulate.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    p_obs = sub.add_parser("observability", help="Observability exports and trend checks")
    obs_sub = p_obs.add_subparsers(dest="observability_command", required=True)
    p_obs_report = obs_sub.add_parser("report", help="Export observability metrics with trend checks")
    p_obs_report.add_argument("--output", type=Path, help="Optional output path for JSON report")
    p_obs_report.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_obs_report.add_argument("--check", action="store_true", help="Exit non-zero when trend status is warn/critical")

    p_handoff = sub.add_parser("handoff", help="Canonical handoff envelope commands")
    handoff_sub = p_handoff.add_subparsers(dest="handoff_command", required=True)
    p_handoff_validate = handoff_sub.add_parser("validate", help="Validate a handoff payload file")
    p_handoff_validate.add_argument("--input", type=Path, required=True, help="Path to JSON or YAML payload file")
    p_handoff_validate.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    p_edge = sub.add_parser("edge", help="Edge telemetry and trace inspection")
    edge_sub = p_edge.add_subparsers(dest="edge_command", required=True)
    p_edge_health = edge_sub.add_parser("health", help="Compute edge health metrics from trace logs")
    p_edge_health.add_argument("--window", type=int, default=200, help="Window size (last N traces)")
    p_edge_health.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_edge_trace = edge_sub.add_parser("trace", help="Fetch a trace bundle by trace_id")
    p_edge_trace.add_argument("--trace-id", required=True, help="Trace identifier")
    p_edge_trace.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    p_migrate = sub.add_parser("migrate", help="Migrate registry/governance to current schema")
    migrate_sub = p_migrate.add_subparsers(dest="migrate_command", required=True)
    p_mig_registry = migrate_sub.add_parser("registry", help="Migrate registry JSON")
    p_mig_registry.add_argument("--input", type=Path, default=None, help="Input registry path")
    p_mig_registry.add_argument("--output", type=Path, default=None, help="Output path (defaults to input path)")
    p_mig_registry.add_argument("--in-place", action="store_true", help="Write migration output over input file")
    p_mig_governance = migrate_sub.add_parser("governance", help="Migrate governance JSON")
    p_mig_governance.add_argument("--input", type=Path, default=None, help="Input governance path")
    p_mig_governance.add_argument("--output", type=Path, default=None, help="Output path (defaults to input path)")
    p_mig_governance.add_argument("--in-place", action="store_true", help="Write migration output over input file")

    # ----- Patchbay command -----
    p_patch = sub.add_parser("patch", help="Patchbay — command center briefing")
    p_patch.add_argument("section", nargs="?", choices=["pulse", "queue", "stats"],
                         help="Show only one section (default: full briefing)")
    p_patch.add_argument("--json", action="store_true", dest="json_output",
                         help="Machine-readable JSON output")
    p_patch.add_argument("--organ", help="Filter to one organ (e.g., III, META)")
    p_patch.add_argument("--watch", action="store_true", help="Real-time watch mode (updates every 5s)")

    p_graph = sub.add_parser("graph", help="Generate Galactic Registry Graph (Mermaid.js)")
    p_graph.add_argument("--live", action="store_true", help="Watch mode for live terminal updates")
    p_graph.add_argument("--output", type=Path, help="Write output to file")

    sub.add_parser("clusters", help="List all clusters")
    sub.add_parser("domains", help="List all domains")
    sub.add_parser("version", help="Show conductor version")

    # ----- Oracle commands -----
    p_oracle = sub.add_parser("oracle", help="Guardian Angel — contextual advisory engine")
    oracle_sub = p_oracle.add_subparsers(dest="oracle_command", required=True)
    p_oracle_consult = oracle_sub.add_parser("consult", help="Full advisory with narratives")
    p_oracle_consult.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_oracle_gate = oracle_sub.add_parser("gate", help="Decision-gate check")
    p_oracle_gate.add_argument("--trigger", required=True, help="Trigger type (e.g., phase_transition, promotion)")
    p_oracle_gate.add_argument("--target", help="Target phase or state")
    p_oracle_gate.add_argument("--repo", help="Repo for promotion gates")
    p_oracle_gate.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_oracle_wisdom = oracle_sub.add_parser("wisdom", help="Deep narrative wisdom")
    p_oracle_wisdom.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_oracle_status = oracle_sub.add_parser("status", help="Detector effectiveness scores")
    p_oracle_status.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_oracle_history = oracle_sub.add_parser("history", help="Recent advisory log")
    p_oracle_history.add_argument("--limit", type=int, default=20, help="Number of entries to show")
    p_oracle_history.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_oracle_ack = oracle_sub.add_parser("ack", help="Acknowledge (suppress) an advisory")
    p_oracle_ack.add_argument("advisory_hash", help="Advisory hash to acknowledge")
    p_oracle_profile = oracle_sub.add_parser("profile", help="Behavioral profile from cross-session analysis")
    p_oracle_profile.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_oracle_detectors = oracle_sub.add_parser("detectors", help="List all detectors with metadata and effectiveness")
    p_oracle_detectors.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_oracle_trends = oracle_sub.add_parser("trends", help="Ship rate, duration, and phase balance trends")
    p_oracle_trends.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_oracle_calibrate = oracle_sub.add_parser("calibrate", help="Calibrate a detector's effectiveness score")
    p_oracle_calibrate.add_argument("detector", help="Detector name")
    p_oracle_calibrate.add_argument("--action", choices=["reset", "boost", "penalize"], default="reset", help="Calibration action")
    p_oracle_export = oracle_sub.add_parser("export", help="Full export of oracle state, profile, and manifest")
    p_oracle_export.add_argument("--output", type=Path, help="Write to file instead of stdout")
    p_oracle_diagnose = oracle_sub.add_parser("diagnose", help="Self-diagnostic: detector health, state integrity")

    # Guardian Angel subcommands
    p_oracle_counsel = oracle_sub.add_parser("counsel", help="Guardian Angel enhanced consult with wisdom enrichment")
    p_oracle_counsel.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_oracle_teach = oracle_sub.add_parser("teach", help="On-demand teaching of a principle")
    p_oracle_teach.add_argument("topic", help="Topic or principle ID to look up (e.g., tdd, SOLID, mvp)")
    p_oracle_teach.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_oracle_landscape = oracle_sub.add_parser("landscape", help="Risk-reward landscape mapping for a decision")
    p_oracle_landscape.add_argument("decision", help="Decision description (e.g., 'rewrite vs refactor')")
    p_oracle_landscape.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_oracle_whisper = oracle_sub.add_parser("whisper", help="Quick ambient guidance check for an action")
    p_oracle_whisper.add_argument("action", help="Action description to check")
    p_oracle_whisper.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_oracle_mastery = oracle_sub.add_parser("mastery", help="Growth and mastery report")
    p_oracle_mastery.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    p_oracle_corpus = oracle_sub.add_parser("corpus", help="Browse or search the wisdom corpus")
    p_oracle_corpus.add_argument("--search", help="Optional search query")
    p_oracle_corpus.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    # ----- Wiring commands -----
    p_wiring = sub.add_parser("wiring", help="Workspace-wide integration")
    wiring_sub = p_wiring.add_subparsers(dest="wiring_command", required=True)
    p_w_inject = wiring_sub.add_parser("inject", help="Inject Conductor hooks into all repositories")
    p_w_inject.add_argument("--apply", action="store_true", help="Apply changes (default is dry-run)")
    p_w_mcp = wiring_sub.add_parser("mcp", help="Configure global Conductor MCP server")
    p_w_mcp.add_argument("--apply", action="store_true", help="Apply changes (default is dry-run)")

    return parser
