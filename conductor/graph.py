"""Layer 4: Galactic Registry Graph — Visual intelligence for the meta-workspace."""

from __future__ import annotations

from typing import Any
from .governance import GovernanceRuntime
from .constants import organ_short


class RegistryGraph:
    """Generates Mermaid.js visual representations of the system state."""

    def __init__(self, gov: GovernanceRuntime):
        self.gov = gov

    def generate_mermaid(self) -> str:
        """Generate a complete Mermaid flowchart of the registry."""
        lines = [
            "graph TD",
            "    %% System Configuration",
            "    classDef organ fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#fff;",
            "    classDef status_local fill:#2d3748,stroke:#4a4a4a,color:#e2e8f0;",
            "    classDef status_cand fill:#2b6cb0,stroke:#4299e1,color:#ebf8ff;",
            "    classDef status_pub fill:#2f855a,stroke:#63b3ed,color:#ebf8ff;",
            "    classDef status_grad fill:#276749,stroke:#48bb78,color:#f0fff4;",
            "    classDef status_arch fill:#718096,stroke:#a0aec0,color:#edf2f7;",
            "    classDef violation fill:#9b2c2c,stroke:#fc8181,stroke-width:3px,color:#fff;",
            "",
            "    %% System Node",
            "    SYS[ORGANVM Meta-Workspace]:::organ",
            ""
        ]

        organs = self.gov.registry.get("organs", {})
        
        for organ_key, organ_data in sorted(organs.items()):
            short_name = organ_short(organ_key)
            name = organ_data.get("name", short_name)
            repos = organ_data.get("repositories", [])
            
            # Count WIP
            cand_count = sum(1 for r in repos if r.get("promotion_status") == "CANDIDATE")
            pub_count = sum(1 for r in repos if r.get("promotion_status") == "PUBLIC_PROCESS")
            
            cand_violation = cand_count > self.gov.max_candidate_per_organ
            pub_violation = pub_count > self.gov.max_public_process_per_organ
            
            organ_class = "violation" if (cand_violation or pub_violation) else "organ"
            
            lines.append(f"    subgraph {organ_key} [\"{short_name}: {name}\"]")
            
            # Group repos by status
            grouped: dict[str, list[str]] = {
                "LOCAL": [], "CANDIDATE": [], "PUBLIC_PROCESS": [], "GRADUATED": [], "ARCHIVED": []
            }
            for repo in repos:
                status = repo.get("promotion_status", "LOCAL")
                if status in grouped:
                    grouped[status].append(repo.get("name", "unknown"))
            
            for status, repo_names in grouped.items():
                if not repo_names:
                    continue
                
                status_slug = status.lower()
                lines.append(f"        subgraph {organ_key}_{status} [\"{status}\"]")
                for repo_name in repo_names:
                    node_id = f"{organ_key}_{repo_name}".replace("-", "_").replace(".", "_")
                    lines.append(f"            {node_id}[\"{repo_name}\"]:::status_{status_slug[:4]}")
                lines.append("        end")
            
            lines.append("    end")
            lines.append(f"    SYS --- {organ_key}")
            lines.append("")

        return "\n".join(lines)
