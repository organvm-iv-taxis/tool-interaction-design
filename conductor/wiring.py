"""Layer 5: Wiring & Injection — The meta-workspace nervous system."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .constants import ORGANS, WORKSPACE, resolve_organ_key, organ_short
from .governance import GovernanceRuntime
from .observability import log_event

CONDUCTOR_HOOK = """
## ⚡ Conductor OS Integration
This repository is a managed component of the ORGANVM meta-workspace.
- **Orchestration:** Use `conductor patch` for system status and work queue.
- **Lifecycle:** Follow the `FRAME -> SHAPE -> BUILD -> PROVE` workflow.
- **Governance:** Promotions are managed via `conductor wip promote`.
- **Intelligence:** Conductor MCP tools are available for routing and mission synthesis.
"""

class WiringEngine:
    def __init__(self, gov: GovernanceRuntime):
        self.gov = gov

    def _get_repo_path(self, organ_key: str, repo_name: str) -> Optional[Path]:
        """Calculate the absolute path to a repo based on workspace conventions."""
        organ_shorthand = organ_short(organ_key)
        organ_meta = ORGANS.get(organ_shorthand)
        if not organ_meta:
            return None
        
        repo_path = WORKSPACE / organ_meta["dir"] / repo_name
        return repo_path if repo_path.exists() else None

    def inject_all(self, dry_run: bool = True) -> dict[str, Any]:
        """Inject Conductor awareness into every repo in the registry."""
        results = {"injected": [], "skipped": [], "errors": []}
        
        for organ_key, repo_dict in self.gov._all_repos():
            repo_name = repo_dict.get("name")
            path = self._get_repo_path(organ_key, repo_name)
            
            if not path:
                results["skipped"].append(f"{repo_name} (path not found)")
                continue

            try:
                self._inject_into_repo(path, dry_run)
                results["injected"].append(repo_name)
            except Exception as e:
                results["errors"].append(f"{repo_name}: {str(e)}")

        log_event("wiring.inject_all", {"count": len(results["injected"]), "dry_run": dry_run})
        return results

    def _inject_into_repo(self, repo_path: Path, dry_run: bool) -> None:
        """Inject the Conductor hook into GEMINI.md and CLAUDE.md."""
        for filename in ["GEMINI.md", "CLAUDE.md"]:
            target = repo_path / filename
            if not target.exists():
                if dry_run:
                    print(f"  [DRY RUN] Would create {target}")
                else:
                    target.write_text(f"# {repo_path.name}\n{CONDUCTOR_HOOK}")
                continue

            content = target.read_text()
            if "Conductor OS Integration" in content:
                continue

            if dry_run:
                print(f"  [DRY RUN] Would inject into {target}")
            else:
                # Append to end of file
                new_content = content.rstrip() + "\n\n" + CONDUCTOR_HOOK
                target.write_text(new_content)
                print(f"  [INJECTED] {target}")

    def global_mcp_setup(self, dry_run: bool = True) -> str:
        """Update global agent settings to include Conductor MCP."""
        # Standard locations for Claude/Gemini settings
        settings_paths = [
            Path.home() / ".claude" / "settings.json",
            Path.home() / ".gemini" / "settings.json",
        ]
        
        conductor_mcp_config = {
            "command": "python3",
            "args": [str(Path(__file__).parent.parent / "mcp_server.py")],
            "env": {
                "ORGANVM_WORKSPACE_DIR": str(WORKSPACE)
            }
        }

        found_any = False
        for p in settings_paths:
            if p.exists():
                found_any = True
                if dry_run:
                    print(f"  [DRY RUN] Would add Conductor to {p}")
                else:
                    try:
                        data = json.loads(p.read_text())
                        mcp_servers = data.setdefault("mcpServers", {})
                        mcp_servers["conductor"] = conductor_mcp_config
                        p.write_text(json.dumps(data, indent=2))
                        print(f"  [UPDATED] {p}")
                    except Exception as e:
                        print(f"  [ERROR] Could not update {p}: {e}")

        if not found_any:
            return "No agent settings files found to update."
        return "Global MCP setup complete."
