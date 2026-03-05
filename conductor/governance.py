"""Layer 2: Governance Runtime — registry sync, WIP enforcement, staleness, audit."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from .constants import (
    GENERATED_DIR,
    GOVERNANCE_PATH,
    ORGANS,
    PROMOTION_STATES,
    PROMOTION_TRANSITIONS,
    REGISTRY_PATH,
    WORKSPACE,
    GovernanceError,
    atomic_write,
    organ_short,
    resolve_organ_key,
)
from .observability import log_event
from .policy import Policy, load_policy
from .schemas import validate_document


@dataclass(frozen=True)
class RepoRecord:
    """Typed boundary model for repo entries in registry JSON."""

    name: str
    promotion_status: str | None
    raw: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: Any, *, organ_key: str, index: int) -> RepoRecord:
        if not isinstance(payload, dict):
            raise GovernanceError(
                f"Registry schema error: organs.{organ_key}.repositories[{index}] must be an object"
            )
        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            raise GovernanceError(
                f"Registry schema error: organs.{organ_key}.repositories[{index}].name must be a non-empty string"
            )
        promotion_status = payload.get("promotion_status")
        if promotion_status is not None and not isinstance(promotion_status, str):
            raise GovernanceError(
                f"Registry schema error: organs.{organ_key}.repositories[{index}].promotion_status must be a string"
            )
        if "dependencies" in payload and payload["dependencies"] is not None and not isinstance(payload["dependencies"], list):
            raise GovernanceError(
                f"Registry schema error: organs.{organ_key}.repositories[{index}].dependencies must be a list"
            )
        if "ci_workflow" in payload and payload["ci_workflow"] is not None and not isinstance(payload["ci_workflow"], str):
            raise GovernanceError(
                f"Registry schema error: organs.{organ_key}.repositories[{index}].ci_workflow must be a string"
            )
        if "last_validated" in payload and payload["last_validated"] is not None and not isinstance(payload["last_validated"], str):
            raise GovernanceError(
                f"Registry schema error: organs.{organ_key}.repositories[{index}].last_validated must be a string"
            )
        normalized = dict(payload)
        if normalized.get("dependencies") is None:
            normalized["dependencies"] = []
        if normalized.get("ci_workflow") is None:
            normalized["ci_workflow"] = ""
        if normalized.get("last_validated") is None:
            normalized["last_validated"] = ""
        return cls(name=name.strip(), promotion_status=promotion_status, raw=normalized)


def _parse_registry_payload(payload: Any) -> dict:
    """Validate and normalize registry JSON payload."""
    if not isinstance(payload, dict):
        raise GovernanceError("Registry schema error: top-level payload must be an object")

    organs_raw = payload.get("organs", {})
    if organs_raw is None:
        organs_raw = {}
    if not isinstance(organs_raw, dict):
        raise GovernanceError("Registry schema error: top-level 'organs' must be an object")

    normalized_organs: dict[str, dict[str, Any]] = {}
    for organ_key, organ_data in organs_raw.items():
        if not isinstance(organ_key, str) or not organ_key.strip():
            raise GovernanceError("Registry schema error: organ keys must be non-empty strings")
        if not isinstance(organ_data, dict):
            raise GovernanceError(f"Registry schema error: organs.{organ_key} must be an object")

        repos_raw = organ_data.get("repositories", [])
        if repos_raw is None:
            repos_raw = []
        if not isinstance(repos_raw, list):
            raise GovernanceError(f"Registry schema error: organs.{organ_key}.repositories must be a list")

        normalized_repos: list[dict[str, Any]] = []
        for idx, repo_payload in enumerate(repos_raw):
            repo = RepoRecord.from_payload(repo_payload, organ_key=organ_key, index=idx)
            normalized_repos.append(repo.raw)

        normalized_organ = dict(organ_data)
        normalized_organ["repositories"] = normalized_repos
        normalized_organs[organ_key] = normalized_organ

    normalized = dict(payload)
    normalized["organs"] = normalized_organs
    return normalized


def _parse_governance_payload(payload: Any) -> dict:
    """Validate and normalize governance rules JSON payload."""
    if not isinstance(payload, dict):
        raise GovernanceError("Governance schema error: top-level payload must be an object")

    organ_requirements = payload.get("organ_requirements", {})
    if organ_requirements is None:
        organ_requirements = {}
    if not isinstance(organ_requirements, dict):
        raise GovernanceError("Governance schema error: 'organ_requirements' must be an object")

    for organ_key, requirements in organ_requirements.items():
        if not isinstance(requirements, dict):
            raise GovernanceError(f"Governance schema error: organ_requirements.{organ_key} must be an object")
        for key in ("requires_tests", "requires_revenue_fields"):
            if key in requirements and not isinstance(requirements[key], bool):
                raise GovernanceError(
                    f"Governance schema error: organ_requirements.{organ_key}.{key} must be boolean"
                )

    for optional_dict_key in ("dependency_rules", "promotion_rules"):
        value = payload.get(optional_dict_key)
        if value is not None and not isinstance(value, dict):
            raise GovernanceError(f"Governance schema error: '{optional_dict_key}' must be an object")

    normalized = dict(payload)
    normalized["organ_requirements"] = organ_requirements
    return normalized


class GovernanceRuntime:
    """Layer 2: Registry sync, WIP enforcement, staleness, audit."""

    def __init__(self, confirm_fn: Optional[Callable[[str], bool]] = None, *, offline: bool = False) -> None:
        # Capture paths at construction time so patches during __init__
        # carry through to all subsequent method calls.
        self._registry_path: Path = REGISTRY_PATH
        self._governance_path: Path = GOVERNANCE_PATH
        self._offline: bool = offline
        self.registry: dict = {}
        self.governance: dict = {}
        self.policy: Policy = load_policy()
        # WIP limit precedence: policy bundle > governance-rules.json > constants.py
        self.max_candidate_per_organ = self.policy.max_candidate_per_organ
        self.max_public_process_per_organ = self.policy.max_public_process_per_organ
        self.confirm_fn: Callable[[str], bool] = confirm_fn or self._default_confirm
        self._load()
        # After loading governance, apply per-organ overrides from governance-rules.json
        gov_wip = self.governance.get("wip_limits", {})
        if isinstance(gov_wip, dict):
            # governance-rules.json can override defaults but policy bundle wins
            if not self.policy.name or self.policy.name == "default":
                if "max_candidate_per_organ" in gov_wip:
                    self.max_candidate_per_organ = int(gov_wip["max_candidate_per_organ"])
                if "max_public_process_per_organ" in gov_wip:
                    self.max_public_process_per_organ = int(gov_wip["max_public_process_per_organ"])

    @staticmethod
    def _default_confirm(prompt: str) -> bool:
        answer = input(f"  {prompt} [y/N] ")
        return answer.lower() in ("y", "yes")

    # Path to local cache of last-known-good corpus data
    _CORPUS_CACHE_DIR = Path(__file__).parent.parent / ".conductor-corpus-cache"

    def _cache_corpus(self) -> None:
        """Cache current corpus data locally for offline fallback."""
        try:
            self._CORPUS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            if self.registry:
                (self._CORPUS_CACHE_DIR / "registry-v2.json").write_text(
                    json.dumps(self.registry, indent=2)
                )
            if self.governance:
                (self._CORPUS_CACHE_DIR / "governance-rules.json").write_text(
                    json.dumps(self.governance, indent=2)
                )
        except OSError:
            pass

    def _load_from_cache(self) -> bool:
        """Load corpus from local cache. Returns True if cache was available."""
        cache_reg = self._CORPUS_CACHE_DIR / "registry-v2.json"
        cache_gov = self._CORPUS_CACHE_DIR / "governance-rules.json"
        loaded = False
        if cache_reg.exists():
            try:
                self.registry = _parse_registry_payload(json.loads(cache_reg.read_text()))
                loaded = True
            except Exception:
                pass
        if cache_gov.exists():
            try:
                self.governance = _parse_governance_payload(json.loads(cache_gov.read_text()))
                loaded = True
            except Exception:
                pass
        return loaded

    def _load(self) -> None:
        corpus_available = self._registry_path.exists() or self._governance_path.exists()

        if self._offline or not corpus_available:
            # Offline mode: use cached corpus if available
            if self._load_from_cache():
                log_event(
                    "governance.load",
                    {
                        "registry_loaded": bool(self.registry),
                        "governance_loaded": bool(self.governance),
                        "policy_bundle": self.policy.name,
                        "source": "cache",
                    },
                )
                return
            # No cache either — operate with empty state
            log_event(
                "governance.load",
                {
                    "registry_loaded": False,
                    "governance_loaded": False,
                    "policy_bundle": self.policy.name,
                    "source": "empty",
                },
            )
            return

        if self._registry_path.exists():
            try:
                raw_registry = json.loads(self._registry_path.read_text())
                schema_issues = validate_document("registry", raw_registry)
                if schema_issues:
                    summary = "; ".join(
                        f"{issue.code} {issue.path}: {issue.message}"
                        for issue in schema_issues[:3]
                    )
                    raise GovernanceError(f"Registry schema validation failed: {summary}")
                self.registry = _parse_registry_payload(raw_registry)
            except json.JSONDecodeError as e:
                raise GovernanceError(f"Invalid JSON in registry file {self._registry_path}: {e}") from e

        if self._governance_path.exists():
            try:
                raw_governance = json.loads(self._governance_path.read_text())
                schema_issues = validate_document("governance", raw_governance)
                if schema_issues:
                    summary = "; ".join(
                        f"{issue.code} {issue.path}: {issue.message}"
                        for issue in schema_issues[:3]
                    )
                    raise GovernanceError(f"Governance schema validation failed: {summary}")
                self.governance = _parse_governance_payload(raw_governance)
            except json.JSONDecodeError as e:
                raise GovernanceError(f"Invalid JSON in governance file {self._governance_path}: {e}") from e

        # Cache successfully loaded corpus for future offline use
        self._cache_corpus()

        log_event(
            "governance.load",
            {
                "registry_loaded": self._registry_path.exists(),
                "governance_loaded": self._governance_path.exists(),
                "policy_bundle": self.policy.name,
                "source": "corpus",
            },
        )

    def _all_repos(self) -> list[tuple[str, dict]]:
        """Return (organ_key, repo_dict) for every repo in registry."""
        results = []
        for organ_key, organ_data in self.registry.get("organs", {}).items():
            for repo in organ_data.get("repositories", []):
                results.append((organ_key, repo))
        return results

    def _trigger_work_registry_sync(self) -> None:
        """Refresh the stateful WorkRegistry after a mutation."""
        try:
            from .work_item import WorkRegistry
            from .workqueue import WorkQueue
            WorkRegistry().sync(WorkQueue(self).compute())
        except Exception as e:
            log_event("governance.sync_trigger_failed", {"error": str(e)})

    # ----- Registry Sync -----

    def registry_sync(self, fix: bool = False, dry_run: bool = False) -> None:
        """Compare GitHub API repos vs registry, report delta. With --fix, auto-add missing."""
        print(f"\n  Registry Sync {'(DRY RUN)' if dry_run else ''}")
        print("  " + "=" * 50)

        all_repos = self._all_repos()
        registry_names = {repo.get("name") for _, repo in all_repos}
        
        # Group by org for batched queries
        missing_repos = []
        for short_key, meta in ORGANS.items():
            org = meta["org"]
            reg_key = meta["registry_key"]
            
            print(f"  Checking GitHub org: {org}...")
            try:
                result = subprocess.run(
                    ["gh", "repo", "list", org, "--json", "name", "--limit", "200"],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode != 0:
                    print(f"    WARNING: Could not list repos for {org}: {result.stderr.strip()}")
                    continue
                
                gh_names = {r["name"] for r in json.loads(result.stdout)}
                delta = gh_names - registry_names
                
                for name in sorted(delta):
                    missing_repos.append((reg_key, name))
                    print(f"    [MISSING] {name} (should be in {reg_key})")
            except (subprocess.TimeoutExpired, FileNotFoundError):
                print(f"    WARNING: gh CLI unavailable or timed out for {org}")

        if not missing_repos:
            print("\n  Registry is in sync with GitHub.")
            return

        print(f"\n  Found {len(missing_repos)} repos on GitHub missing from registry.")
        
        if fix and not dry_run:
            if not self.confirm_fn(f"Add {len(missing_repos)} missing repos to registry?"):
                print("  Aborted.")
                return

            for reg_key, name in missing_repos:
                organ_data = self.registry.get("organs", {}).get(reg_key)
                if organ_data:
                    organ_data.setdefault("repositories", []).append({
                        "name": name,
                        "promotion_status": "LOCAL",
                        "tier": "standard",
                        "documentation_status": "EMPTY",
                        "implementation_status": "STUB",
                        "ci_workflow": "",
                        "dependencies": [],
                        "last_validated": datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    })

            if self._registry_path.exists():
                shutil.copy2(self._registry_path, self._registry_path.with_suffix(".json.bak"))
            atomic_write(self._registry_path, json.dumps(self.registry, indent=2) + "\n")
            print(f"  Added {len(missing_repos)} repos. Registry updated.")
            self._trigger_work_registry_sync()
        elif fix:
            print(f"  Dry run: would add {len(missing_repos)} repos.")
        else:
            print("  Run with --fix to automatically add these to the registry.")
        print()

    def wip_check(self, organ: Optional[str] = None) -> None:
        """Check all organs against WIP limits and report violations."""
        print(f"\n  WIP Check: {organ or 'FULL SYSTEM'}")
        print("  " + "=" * 50)

        organs_to_check = {}
        if organ:
            key = resolve_organ_key(organ)
            if key in self.registry.get("organs", {}):
                organs_to_check[key] = self.registry["organs"][key]
            else:
                raise GovernanceError(f"Organ '{organ}' not found in registry.")
        else:
            organs_to_check = self.registry.get("organs", {})

        violations = []
        warnings = []
        
        for organ_key, organ_data in organs_to_check.items():
            repos = organ_data.get("repositories", [])
            counts = Counter(r.get("promotion_status", "UNKNOWN") for r in repos)
            
            cand = counts.get("CANDIDATE", 0)
            pub = counts.get("PUBLIC_PROCESS", 0)
            
            cand_limit = self.max_candidate_per_organ
            pub_limit = self.max_public_process_per_organ
            
            short = organ_short(organ_key)
            
            # CANDIDATE
            if cand > cand_limit:
                violations.append(f"[{short}] CAND>{cand_limit} ({cand}/{cand_limit})")
            elif cand >= cand_limit * 0.8:
                warnings.append(f"[{short}] CAND approaching limit ({cand}/{cand_limit})")
            
            # PUBLIC_PROCESS
            if pub > pub_limit:
                violations.append(f"[{short}] PUBLIC_PROCESS (PUB>{pub_limit}) violation: {pub}/{pub_limit}")
            elif pub >= pub_limit * 0.8:
                warnings.append(f"[{short}] PUBLIC_PROCESS (PUB) approaching limit ({pub}/{pub_limit})")

        if violations:
            print("\n  WIP VIOLATIONS")
            print("  " + "-" * 20)
            for v in violations:
                print(f"  !! {v}")
        
        if warnings:
            print("\n  WIP WARNINGS")
            print("  " + "-" * 20)
            for w in warnings:
                print(f"  !  {w}")

        if not violations and not warnings:
            print("\n  All organs within WIP limits.")

        print(f"\n  Total violations: {len(violations)}")
        if violations:
            print("  Suggestion: Promote or archive repos to clear the pipeline.")
        print()

    def wip_promote(self, repo_name: str, target_state: str) -> None:
        """Promote a repo with WIP limit enforcement."""
        target_state = target_state.upper()
        if target_state not in PROMOTION_STATES:
            raise GovernanceError(f"Invalid state: {target_state}. Must be one of: {', '.join(PROMOTION_STATES)}")

        # Find repo
        found_repo = None
        found_organ_key = None
        for organ_key, organ_data in self.registry.get("organs", {}).items():
            for repo in organ_data.get("repositories", []):
                if repo.get("name") == repo_name:
                    found_repo = repo
                    found_organ_key = organ_key
                    break
            if found_repo:
                break

        if not found_repo or not found_organ_key:
            raise GovernanceError(f"Repo '{repo_name}' not found in registry.")

        current = str(found_repo.get("promotion_status", "LOCAL")).upper()
        if current == target_state:
            print(f"  Repo '{repo_name}' is already in state {target_state}.")
            return

        # Validate transition
        allowed = PROMOTION_TRANSITIONS.get(current, [])
        if target_state not in allowed:
            raise GovernanceError(f"Cannot transition '{repo_name}' from {current} to {target_state}. Allowed: {', '.join(allowed)}")

        # Check WIP limits
        if target_state in {"CANDIDATE", "PUBLIC_PROCESS"}:
            organ_repos = self.registry["organs"][found_organ_key].get("repositories", [])
            current_count = sum(1 for r in organ_repos if r.get("promotion_status") == target_state)
            limit = self.max_candidate_per_organ if target_state == "CANDIDATE" else self.max_public_process_per_organ
            
            if current_count >= limit:
                raise GovernanceError(f"WIP limit reached for {target_state} in {found_organ_key} ({current_count}/{limit}).")

        # Confirm
        if not self.confirm_fn(f"Promote {repo_name} from {current} to {target_state}?"):
            print("  Aborted.")
            log_event(
                "governance.wip_promote",
                {"repo": repo_name, "current": current, "target": target_state, "aborted": True},
            )
            return

        # After successful promotion:
        found_repo["promotion_status"] = target_state
        found_repo["last_validated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if self._registry_path.exists():
            shutil.copy2(self._registry_path, self._registry_path.with_suffix(".json.bak"))
        atomic_write(self._registry_path, json.dumps(self.registry, indent=2) + "\n")

        print(f"\n  Promoted: {repo_name}")
        print(f"  {current} -> {target_state}")
        print(f"  Registry updated: {self._registry_path}")
        
        self._trigger_work_registry_sync()
        
        log_event(
            "governance.wip_promote",
            {"repo": repo_name, "current": current, "target": target_state, "aborted": False},
        )
        print()

    # ----- Health Signals -----

    @staticmethod
    def _find_repo_path(repo_name: str, organ_key: str = "") -> Path | None:
        """Search the workspace for a repo directory, using organ_key to narrow the search."""
        # If organ_key is provided, look in the matching organ directory first
        if organ_key:
            for meta in ORGANS.values():
                if meta["registry_key"] == organ_key:
                    candidate = WORKSPACE / meta["dir"] / repo_name
                    if candidate.is_dir():
                        return candidate

        # Fallback: scan all organ directories
        for meta in ORGANS.values():
            candidate = WORKSPACE / meta["dir"] / repo_name
            if candidate.is_dir():
                return candidate

        # Check root workspace (personal projects, etc.)
        candidate = WORKSPACE / repo_name
        if candidate.is_dir():
            return candidate

        return None

    @staticmethod
    def _health_signals(repo: dict[str, Any], organ_key: str = "") -> dict[str, bool]:
        """Assess repo health using filesystem checks with registry fallback."""
        repo_name = repo.get("name", "")
        repo_path = GovernanceRuntime._find_repo_path(repo_name, organ_key)

        if repo_path and repo_path.is_dir():
            # Filesystem-based checks
            readme = repo_path / "README.md"
            docs_ok = readme.is_file() and readme.stat().st_size > 500

            workflows_dir = repo_path / ".github" / "workflows"
            ci_ok = workflows_dir.is_dir() and any(workflows_dir.iterdir())

            pkg_name = repo_name.replace("-", "_")
            src_dirs = [d for d in ["src", "lib", pkg_name] if (repo_path / d).is_dir()]
            test_dirs = [d for d in ["tests", "test"] if (repo_path / d).is_dir()]
            impl_ok = bool(src_dirs) and bool(test_dirs)
        else:
            # Fallback to registry field checks
            docs_ok = str(repo.get("documentation_status", "")).upper() == "DEPLOYED"
            ci_ok = bool(str(repo.get("ci_workflow", "")).strip())
            impl_ok = str(repo.get("implementation_status", "")).upper() in {
                "ACTIVE", "COMPLETE", "COMPLETED", "READY", "MATURE", "STABLE",
            }

        return {
            "docs_ok": docs_ok,
            "ci_ok": ci_ok,
            "implementation_ok": impl_ok,
        }

    def auto_promote(self, dry_run: bool = True) -> dict[str, Any]:
        """Auto-promote healthy repos while respecting WIP limits.

        Rules:
        - LOCAL -> CANDIDATE when docs/CI/implementation all look healthy.
        - CANDIDATE -> PUBLIC_PROCESS when docs/CI/implementation all look healthy.
        - Never violate per-organ WIP limits.
        """
        all_repos = self._all_repos()
        counts: dict[str, Counter] = defaultdict(Counter)
        for organ_key, repo in all_repos:
            counts[organ_key][repo.get("promotion_status", "UNKNOWN")] += 1

        proposed: list[dict[str, Any]] = []
        promoted: list[dict[str, Any]] = []
        today = datetime.now().strftime("%Y-%m-%d")

        for organ_key, repo in sorted(all_repos, key=lambda pair: (pair[0], pair[1].get("name", ""))):
            current = str(repo.get("promotion_status", "LOCAL")).upper()
            if current == "LOCAL":
                target = "CANDIDATE"
            elif current == "CANDIDATE":
                target = "PUBLIC_PROCESS"
            else:
                continue

            signals = self._health_signals(repo, organ_key)
            if not all(signals.values()):
                continue

            if target == "CANDIDATE" and counts[organ_key]["CANDIDATE"] >= self.max_candidate_per_organ:
                continue
            if (
                target == "PUBLIC_PROCESS"
                and counts[organ_key]["PUBLIC_PROCESS"] >= self.max_public_process_per_organ
            ):
                continue

            row = {
                "organ": organ_key,
                "repo": repo.get("name"),
                "current": current,
                "target": target,
                "signals": signals,
            }
            proposed.append(row)

            counts[organ_key][current] -= 1
            counts[organ_key][target] += 1

            if dry_run:
                continue

            repo["promotion_status"] = target
            repo["last_validated"] = today
            promoted.append(row)

        if promoted and not dry_run:
            if self._registry_path.exists():
                shutil.copy2(self._registry_path, self._registry_path.with_suffix(".json.bak"))
            atomic_write(self._registry_path, json.dumps(self.registry, indent=2) + "\n")

        summary = {
            "dry_run": dry_run,
            "policy_bundle": self.policy.name,
            "limits": {
                "max_candidate_per_organ": self.max_candidate_per_organ,
                "max_public_process_per_organ": self.max_public_process_per_organ,
            },
            "eligible": len(proposed),
            "promoted": len(promoted),
        }

        payload = {
            "summary": summary,
            "proposed": proposed,
            "promoted": promoted,
        }
        log_event("governance.auto_promote", summary)
        return payload

    # ----- Staleness (batched via GraphQL) -----

    def stale(self, days: int = 30) -> None:
        """Find CANDIDATE repos with no recent push."""
        print(f"\n  Stale CANDIDATE repos (no push in {days}+ days)")
        print("  " + "=" * 50)

        candidates = [
            (ok, r) for ok, r in self._all_repos()
            if r.get("promotion_status") == "CANDIDATE"
        ]

        if not candidates:
            print("  No CANDIDATE repos found.")
            print()
            return

        # Group by org for batched queries
        by_org: dict[str, list[tuple[str, dict]]] = defaultdict(list)
        for organ_key, repo in candidates:
            for meta in ORGANS.values():
                if meta["registry_key"] == organ_key:
                    by_org[meta["org"]].append((organ_key, repo))
                    break

        stale_repos = []
        for org, repos in by_org.items():
            # Batch: fetch all repos for this org at once
            try:
                result = subprocess.run(
                    ["gh", "repo", "list", org, "--json", "name,pushedAt", "--limit", "200"],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    gh_data = {r["name"]: r.get("pushedAt", "") for r in json.loads(result.stdout)}
                    for organ_key, repo in repos:
                        pushed_str = gh_data.get(repo["name"], "")
                        if pushed_str:
                            try:
                                pushed = datetime.fromisoformat(pushed_str.replace("Z", "+00:00"))
                                age = (datetime.now(timezone.utc) - pushed).days
                                if age >= days:
                                    stale_repos.append((organ_key, repo["name"], age))
                            except ValueError:
                                stale_repos.append((organ_key, repo["name"], -1))
                        else:
                            stale_repos.append((organ_key, repo["name"], -1))
            except (subprocess.TimeoutExpired, FileNotFoundError):
                for organ_key, repo in repos:
                    stale_repos.append((organ_key, repo["name"], -1))

        if stale_repos:
            print(f"\n  Found {len(stale_repos)} stale CANDIDATE repos:\n")
            for organ_key, name, age in sorted(stale_repos, key=lambda x: -x[2]):
                age_str = f"{age}d" if age >= 0 else "unknown"
                print(f"    [{organ_short(organ_key)}] {name:<45} last push: {age_str} ago")
            print(f"\n  Suggestion: promote, archive, or work on these repos to unclog the pipeline.")
        else:
            print(f"  No stale CANDIDATE repos (all pushed within {days} days).")
        print()

    # ----- Enforce Generate -----

    def enforce_generate(self, dry_run: bool = False) -> None:
        """Generate GitHub rulesets and Actions from governance-rules.json."""
        print(f"\n  Generating enforcement artifacts {'(DRY RUN)' if dry_run else ''}")
        print("  " + "=" * 50)

        if not self.governance:
            raise GovernanceError("No governance rules loaded.")

        output_dir = GENERATED_DIR
        if not dry_run:
            output_dir.mkdir(exist_ok=True)

        # Read organ-specific requirements from governance
        organ_reqs = self.governance.get("organ_requirements", {})

        artifacts = []

        # 1. Generate org-level rulesets (with organ-specific rules)
        for short_key, meta in ORGANS.items():
            org = meta["org"]
            reg_key = meta["registry_key"]

            status_checks = [{"context": "validate-lifecycle"}]
            reqs = organ_reqs.get(reg_key, {})
            if reqs.get("requires_tests"):
                status_checks.append({"context": "tests"})
            if reqs.get("requires_revenue_fields"):
                status_checks.append({"context": "validate-revenue-fields"})

            ruleset = {
                "name": f"{org}-branch-protection",
                "target": "branch",
                "enforcement": "active",
                "conditions": {
                    "ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []},
                },
                "rules": [
                    {"type": "pull_request", "parameters": {
                        "required_approving_review_count": 0,
                        "dismiss_stale_reviews_on_push": True,
                        "require_last_push_approval": False,
                    }},
                    {"type": "required_status_checks", "parameters": {
                        "strict_required_status_checks_policy": True,
                        "required_status_checks": status_checks,
                    }},
                    {"type": "non_fast_forward"},
                ],
                "organ_requirements": reqs if reqs else None,
            }
            # Remove None values
            ruleset = {k: v for k, v in ruleset.items() if v is not None}
            artifacts.append((f"rulesets/{org}.json", ruleset))

        # 2. Validate-lifecycle workflow
        lifecycle_workflow = {
            "name": "Validate Lifecycle",
            "on": {"pull_request": {"branches": ["main", "master"]}},
            "jobs": {
                "validate": {
                    "runs-on": "ubuntu-latest",
                    "steps": [
                        {"uses": "actions/checkout@v4"},
                        {
                            "name": "Conductor Doctor",
                            "uses": "ivviiviivvi/conductor-action@main",
                            "with": {"command": "doctor", "strict": "true"}
                        },
                        {"name": "Check spec.md exists", "run": "test -f spec.md || test -f docs/spec.md || echo 'No spec.md found'"},
                        {"name": "Check plan.md exists", "run": "test -f plan.md || test -f docs/plan.md || echo 'No plan.md found'"},
                    ],
                }
            },
        }
        artifacts.append(("workflows/validate-lifecycle.yml", lifecycle_workflow))

        # 3. WIP validation workflow
        wip_workflow = {
            "name": "Validate WIP Limits",
            "on": {"workflow_dispatch": {}, "schedule": [{"cron": "0 6 * * 1"}]},
            "jobs": {
                "check-wip": {
                    "runs-on": "ubuntu-latest",
                    "steps": [
                        {"uses": "actions/checkout@v4"},
                        {
                            "name": "Check WIP Limits",
                            "uses": "ivviiviivvi/conductor-action@main",
                            "with": {"command": "wip check"}
                        },
                    ],
                }
            },
        }
        artifacts.append(("workflows/validate-wip.yml", wip_workflow))

        # 4. PR template
        pr_template = """## Summary

<!-- What does this PR do? Reference the Issue. -->

## Governance Checklist

- [ ] spec.md exists and is current
- [ ] plan.md exists and steps are checked off
- [ ] All tests pass
- [ ] No WIP limit violations
- [ ] CHANGELOG updated
- [ ] Conventional commit messages used

## Phase

- [ ] FRAME complete (spec reviewed)
- [ ] SHAPE complete (plan approved)
- [ ] BUILD complete (code + tests)
- [ ] PROVE complete (lint + security + review)
"""
        artifacts.append(("PULL_REQUEST_TEMPLATE.md", pr_template))

        # 5. Issue Form
        issue_form = {
            "name": "Feature Request (Conductor)",
            "description": "Propose a new feature using the FRAME/SHAPE/BUILD/PROVE lifecycle.",
            "body": [
                {"type": "dropdown", "id": "phase", "attributes": {
                    "label": "Current Phase",
                    "options": ["FRAME", "SHAPE", "BUILD", "PROVE"],
                }, "validations": {"required": True}},
                {"type": "input", "id": "organ", "attributes": {
                    "label": "Organ", "placeholder": "e.g., III",
                }, "validations": {"required": True}},
                {"type": "textarea", "id": "scope", "attributes": {
                    "label": "Scope", "placeholder": "What are you building?",
                }, "validations": {"required": True}},
                {"type": "textarea", "id": "acceptance", "attributes": {
                    "label": "Acceptance Criteria",
                }, "validations": {"required": True}},
            ],
        }
        artifacts.append(("ISSUE_TEMPLATE/feature-conductor.yml", issue_form))

        for path, content in artifacts:
            if dry_run:
                print(f"\n  Would generate: {path}")
                if isinstance(content, str):
                    print(f"  ({len(content)} chars)")
                else:
                    print(f"  ({len(json.dumps(content))} chars)")
            else:
                full_path = output_dir / path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(content, str):
                    full_path.write_text(content)
                elif path.endswith(".yml") or path.endswith(".yaml"):
                    full_path.write_text(yaml.dump(content, default_flow_style=False, sort_keys=False))
                else:
                    full_path.write_text(json.dumps(content, indent=2))
                print(f"  Generated: {full_path}")

        total = len(artifacts)
        print(f"\n  {'Would generate' if dry_run else 'Generated'}: {total} artifacts")
        if not dry_run:
            print(f"  Output: {output_dir}/")
        print()

    # ----- Audit -----

    def audit_report(self, organ: Optional[str] = None) -> dict[str, Any]:
        """Structured organ/system health report for machine use."""
        organs_to_check: dict[str, dict[str, Any]] = {}
        if organ:
            key = resolve_organ_key(organ)
            organ_data = self.registry.get("organs", {}).get(key, {})
            if organ_data:
                organs_to_check[key] = organ_data
            else:
                raise GovernanceError(f"Organ '{organ}' not found in registry.")
        else:
            organs_to_check = self.registry.get("organs", {})

        report_organs: dict[str, Any] = {}
        for organ_key, organ_data in organs_to_check.items():
            repos = organ_data.get("repositories", [])
            statuses = Counter(r.get("promotion_status", "UNKNOWN") for r in repos)
            tiers = Counter(r.get("tier", "unknown") for r in repos)
            impl = Counter(r.get("implementation_status", "UNKNOWN") for r in repos)
            missing_readme = [r["name"] for r in repos if r.get("documentation_status", "").upper() == "EMPTY"]
            missing_ci = [r["name"] for r in repos if not r.get("ci_workflow")]
            cand = statuses.get("CANDIDATE", 0)

            recommendations: list[str] = []
            if cand > self.max_candidate_per_organ:
                recommendations.append(
                    f"Triage CANDIDATE repos: promote {cand - self.max_candidate_per_organ}+ to PUBLIC_PROCESS or archive"
                )
            if missing_ci:
                recommendations.append(f"Add CI workflows to {len(missing_ci)} repos")
            if statuses.get("LOCAL", 0) > 0:
                recommendations.append(f"Evaluate {statuses['LOCAL']} LOCAL repos for CANDIDATE promotion")
            if not recommendations:
                recommendations.append("Organ is healthy -- no immediate action needed")

            report_organs[organ_key] = {
                "organ_name": organ_data.get("name", organ_key),
                "organ_short": organ_short(organ_key),
                "total_repos": len(repos),
                "promotion": dict(sorted(statuses.items())),
                "tiers": dict(sorted(tiers.items())),
                "implementation": dict(sorted(impl.items())),
                "missing_readme": missing_readme,
                "missing_ci": missing_ci,
                "wip_violation_candidate": cand > self.max_candidate_per_organ,
                "recommendations": recommendations,
            }

        report = {
            "scope": organ or "FULL SYSTEM",
            "policy_bundle": self.policy.name,
            "limits": {
                "max_candidate_per_organ": self.max_candidate_per_organ,
                "max_public_process_per_organ": self.max_public_process_per_organ,
            },
            "organs": report_organs,
        }
        return report

    def audit(self, organ: Optional[str] = None, create_issues: bool = False) -> None:
        """Full organ or system health report. With create_issues, file GitHub issues for findings."""
        print(f"\n  Audit Report: {organ or 'FULL SYSTEM'}")
        print("  " + "=" * 50)

        report = self.audit_report(organ=organ)
        for organ_key, organ_report in report.get("organs", {}).items():
            print(f"\n  [{organ_report['organ_short']}] {organ_report['organ_name']} -- {organ_report['total_repos']} repos")
            print(f"  {'---' * 17}")

            print(f"  Promotion: " + ", ".join(f"{s}={c}" for s, c in organ_report["promotion"].items()))
            print(f"  Tiers:     " + ", ".join(f"{t}={c}" for t, c in organ_report["tiers"].items()))
            print(f"  Impl:      " + ", ".join(f"{i}={c}" for i, c in organ_report["implementation"].items()))

            if organ_report["missing_readme"]:
                print(f"\n  CRITICAL: {len(organ_report['missing_readme'])} repos missing README:")
                for name in organ_report["missing_readme"][:5]:
                    print(f"    - {name}")

            if organ_report["missing_ci"]:
                print(f"\n  WARNING: {len(organ_report['missing_ci'])} repos without CI:")
                for name in organ_report["missing_ci"][:5]:
                    print(f"    - {name}")

            if organ_report["wip_violation_candidate"]:
                cand = organ_report["promotion"].get("CANDIDATE", 0)
                print(f"\n  WIP VIOLATION: {cand} CANDIDATE (limit {self.max_candidate_per_organ})")

            recs = organ_report["recommendations"]

            print(f"\n  Recommendations:")
            for r in recs:
                print(f"    -> {r}")

            if create_issues and recs and recs[0] != "Organ is healthy -- no immediate action needed":
                self._create_audit_issues(organ_key, recs)

        log_event(
            "governance.audit",
            {
                "scope": report["scope"],
                "organs_checked": len(report["organs"]),
                "policy_bundle": self.policy.name,
            },
        )
        print()

    def _create_audit_issues(self, organ_key: str, recommendations: list[str]) -> None:
        """Create GitHub issues from audit recommendations, skipping duplicates."""
        org = ""
        for meta in ORGANS.values():
            if meta["registry_key"] == organ_key:
                org = meta["org"]
                break
        if not org:
            return

        target_repo = f"{org}/.github"

        # Fetch existing audit issues to avoid duplicates
        existing_titles: set[str] = set()
        try:
            result = subprocess.run(
                ["gh", "issue", "list", "--repo", target_repo,
                 "--label", "conductor-audit", "--json", "title", "--limit", "100"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                for issue in json.loads(result.stdout):
                    existing_titles.add(issue.get("title", ""))
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            pass  # If we can't check, proceed with creation

        for rec in recommendations:
            title = f"[conductor audit] {rec[:80]}"
            if title in existing_titles:
                print(f"    Skipped (duplicate): {title[:60]}...")
                continue

            body = (
                f"## Audit Finding\n\n"
                f"**Organ:** {organ_key}\n"
                f"**Recommendation:** {rec}\n\n"
                f"*Generated by `conductor audit --create-issues`*"
            )
            try:
                result = subprocess.run(
                    ["gh", "issue", "create", "--repo", target_repo,
                     "--title", title, "--body", body, "--label", "conductor-audit"],
                    capture_output=True, text=True, timeout=15,
                )
                if result.returncode == 0:
                    print(f"    Issue created: {result.stdout.strip()}")
                else:
                    print(f"    WARNING: Could not create issue: {result.stderr.strip()}")
            except (subprocess.TimeoutExpired, FileNotFoundError):
                print(f"    WARNING: gh CLI unavailable, skipping issue creation")
