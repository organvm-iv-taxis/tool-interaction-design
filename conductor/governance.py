"""Layer 2: Governance Runtime — registry sync, WIP enforcement, staleness, audit."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import yaml

from .constants import (
    GENERATED_DIR,
    GOVERNANCE_PATH,
    MAX_CANDIDATE_PER_ORGAN,
    MAX_PUBLIC_PROCESS_PER_ORGAN,
    ORGANS,
    PROMOTION_STATES,
    PROMOTION_TRANSITIONS,
    REGISTRY_PATH,
    GovernanceError,
    atomic_write,
    organ_short,
    resolve_organ_key,
)


class GovernanceRuntime:
    """Layer 2: Registry sync, WIP enforcement, staleness, audit."""

    def __init__(self, confirm_fn: Optional[Callable[[str], bool]] = None) -> None:
        self.registry: dict = {}
        self.governance: dict = {}
        self.confirm_fn: Callable[[str], bool] = confirm_fn or self._default_confirm
        self._load()

    @staticmethod
    def _default_confirm(prompt: str) -> bool:
        answer = input(f"  {prompt} [y/N] ")
        return answer.lower() in ("y", "yes")

    def _load(self) -> None:
        if REGISTRY_PATH.exists():
            self.registry = json.loads(REGISTRY_PATH.read_text())

        if GOVERNANCE_PATH.exists():
            self.governance = json.loads(GOVERNANCE_PATH.read_text())

    def _all_repos(self) -> list[tuple[str, dict]]:
        """Return (organ_key, repo_dict) for every repo in registry."""
        results = []
        for organ_key, organ_data in self.registry.get("organs", {}).items():
            for repo in organ_data.get("repositories", []):
                results.append((organ_key, repo))
        return results

    # ----- Registry Sync -----

    def registry_sync(self, fix: bool = False, dry_run: bool = False) -> None:
        """Compare GitHub API repos vs registry, report delta. With --fix, auto-add missing."""
        print("\n  Registry Sync")
        print("  " + "=" * 50)

        github_repos: dict[str, list[str]] = {}
        for short_key, meta in ORGANS.items():
            org = meta["org"]
            try:
                result = subprocess.run(
                    ["gh", "repo", "list", org, "--json", "name", "--limit", "200"],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    repos = json.loads(result.stdout)
                    github_repos[meta["registry_key"]] = [r["name"] for r in repos]
            except (subprocess.TimeoutExpired, FileNotFoundError):
                print(f"  WARNING: Could not fetch repos for {org} (gh CLI unavailable?)")
                github_repos[meta["registry_key"]] = []

        registry_repos: dict[str, set[str]] = {}
        for organ_key, repo in self._all_repos():
            registry_repos.setdefault(organ_key, set()).add(repo["name"])

        total_gh = sum(len(v) for v in github_repos.values())
        total_reg = sum(len(v) for v in registry_repos.values())

        print(f"\n  GitHub API: {total_gh} repos")
        print(f"  Registry:   {total_reg} repos")

        missing_from_registry = []
        for organ_key, gh_names in github_repos.items():
            reg_names = registry_repos.get(organ_key, set())
            for name in gh_names:
                if name not in reg_names:
                    missing_from_registry.append((organ_key, name))

        missing_from_github = []
        for organ_key, reg_names in registry_repos.items():
            gh_names = set(github_repos.get(organ_key, []))
            for name in reg_names:
                if name not in gh_names:
                    missing_from_github.append((organ_key, name))

        if missing_from_registry:
            print(f"\n  Missing from registry ({len(missing_from_registry)}):")
            for organ_key, name in missing_from_registry:
                print(f"    + [{organ_key}] {name}")

            if fix and dry_run:
                print(f"\n  DRY RUN: Would add {len(missing_from_registry)} repos to registry:")
                for organ_key, name in missing_from_registry:
                    print(f"    + [{organ_key}] {name}")
            elif fix:
                print(f"\n  Auto-adding {len(missing_from_registry)} repos to registry...")
                for organ_key, name in missing_from_registry:
                    org_name = ""
                    for meta in ORGANS.values():
                        if meta["registry_key"] == organ_key:
                            org_name = meta["org"]
                            break

                    new_repo = {
                        "name": name,
                        "org": org_name,
                        "status": "ACTIVE",
                        "public": True,
                        "description": "",
                        "documentation_status": "UNKNOWN",
                        "portfolio_relevance": "STANDARD",
                        "dependencies": [],
                        "promotion_status": "LOCAL",
                        "tier": "standard",
                        "last_validated": datetime.now().strftime("%Y-%m-%d"),
                        "implementation_status": "UNKNOWN",
                        "ci_workflow": "",
                        "platinum_status": False,
                    }

                    if organ_key not in self.registry.get("organs", {}):
                        self.registry.setdefault("organs", {})[organ_key] = {"repositories": []}
                    self.registry["organs"][organ_key].setdefault("repositories", []).append(new_repo)
                    print(f"    + Added [{organ_key}] {name}")

                # Save
                if REGISTRY_PATH.exists():
                    shutil.copy2(REGISTRY_PATH, REGISTRY_PATH.with_suffix(".json.bak"))
                atomic_write(REGISTRY_PATH, json.dumps(self.registry, indent=2) + "\n")
                print(f"\n  Registry updated: {REGISTRY_PATH}")
        else:
            print(f"\n  Registry is complete -- all GitHub repos accounted for.")

        if missing_from_github:
            print(f"\n  In registry but not on GitHub ({len(missing_from_github)}):")
            for organ_key, name in missing_from_github:
                print(f"    - [{organ_key}] {name}")

        print()

    # ----- WIP Check -----

    def wip_check(self) -> None:
        """Show WIP counts per organ, flag violations."""
        print("\n  WIP Status")
        print("  " + "=" * 50)

        counts: dict[str, Counter] = defaultdict(Counter)
        for organ_key, repo in self._all_repos():
            status = repo.get("promotion_status", "UNKNOWN")
            counts[organ_key][status] += 1

        total_candidate = 0
        violations = []

        print(f"\n  {'ORGAN':<16} {'LOCAL':>5} {'CAND':>5} {'PUB_P':>5} {'GRAD':>5} {'ARCH':>5} {'FLAGS':>6}")
        print(f"  {'---'*16} {'---'*5} {'---'*5} {'---'*5} {'---'*5} {'---'*5} {'---'*6}")

        for organ_key in sorted(counts.keys()):
            c = counts[organ_key]
            local = c.get("LOCAL", 0)
            cand = c.get("CANDIDATE", 0)
            pub = c.get("PUBLIC_PROCESS", 0)
            grad = c.get("GRADUATED", 0)
            arch = c.get("ARCHIVED", 0)
            total_candidate += cand

            flags = []
            if cand > MAX_CANDIDATE_PER_ORGAN:
                flags.append(f"CAND>{MAX_CANDIDATE_PER_ORGAN}")
                violations.append(f"{organ_key}: {cand} CANDIDATE (limit {MAX_CANDIDATE_PER_ORGAN})")
            if pub > MAX_PUBLIC_PROCESS_PER_ORGAN:
                flags.append(f"PUB>{MAX_PUBLIC_PROCESS_PER_ORGAN}")
                violations.append(f"{organ_key}: {pub} PUBLIC_PROCESS (limit {MAX_PUBLIC_PROCESS_PER_ORGAN})")

            flag_str = ", ".join(flags) if flags else ""
            short = organ_short(organ_key)
            print(f"  {short:<16} {local:>5} {cand:>5} {pub:>5} {grad:>5} {arch:>5}  {flag_str}")

        print(f"\n  Total CANDIDATE across system: {total_candidate}")

        if violations:
            print(f"\n  WIP VIOLATIONS ({len(violations)}):")
            for v in violations:
                print(f"    ! {v}")
        else:
            print(f"  No WIP violations.")
        print()

    # ----- WIP Promote -----

    def wip_promote(self, repo_name: str, target_state: str) -> None:
        """Promote a repo with WIP limit enforcement."""
        target_state = target_state.upper()

        if target_state not in PROMOTION_STATES:
            raise GovernanceError(
                f"Invalid state '{target_state}'. Valid: {', '.join(sorted(PROMOTION_STATES))}"
            )

        all_repos = self._all_repos()

        found = None
        for organ_key, repo in all_repos:
            if repo["name"] == repo_name:
                found = (organ_key, repo)
                break

        if not found:
            raise GovernanceError(f"Repo '{repo_name}' not found in registry.")

        organ_key, repo = found
        current = repo.get("promotion_status", "LOCAL")

        if target_state not in PROMOTION_TRANSITIONS.get(current, []):
            valid = PROMOTION_TRANSITIONS.get(current, [])
            raise GovernanceError(
                f"Cannot transition {current} -> {target_state}. "
                f"Valid transitions: {', '.join(valid or ['none'])}"
            )

        if target_state == "CANDIDATE":
            cand_count = sum(
                1 for ok, r in all_repos
                if ok == organ_key and r.get("promotion_status") == "CANDIDATE"
            )
            if cand_count >= MAX_CANDIDATE_PER_ORGAN:
                raise GovernanceError(
                    f"{organ_key} already has {cand_count} CANDIDATE repos "
                    f"(limit {MAX_CANDIDATE_PER_ORGAN}). Promote or archive existing CANDIDATE repos first."
                )

        if target_state == "PUBLIC_PROCESS":
            pub_count = sum(
                1 for ok, r in all_repos
                if ok == organ_key and r.get("promotion_status") == "PUBLIC_PROCESS"
            )
            if pub_count >= MAX_PUBLIC_PROCESS_PER_ORGAN:
                raise GovernanceError(
                    f"{organ_key} already has {pub_count} PUBLIC_PROCESS repos "
                    f"(limit {MAX_PUBLIC_PROCESS_PER_ORGAN}). Graduate or archive existing PUBLIC_PROCESS repos first."
                )

        if not self.confirm_fn(f"Promote {repo_name}: {current} -> {target_state}?"):
            print("  Aborted.")
            return

        repo["promotion_status"] = target_state
        repo["last_validated"] = datetime.now().strftime("%Y-%m-%d")

        if REGISTRY_PATH.exists():
            shutil.copy2(REGISTRY_PATH, REGISTRY_PATH.with_suffix(".json.bak"))
        atomic_write(REGISTRY_PATH, json.dumps(self.registry, indent=2) + "\n")

        print(f"\n  Promoted: {repo_name}")
        print(f"  {current} -> {target_state}")
        print(f"  Registry updated: {REGISTRY_PATH}")
        print()

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
                        {"name": "Install conductor", "run": "pip install pyyaml"},
                        {"name": "Check WIP", "run": "python3 -m conductor wip check"},
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

    def audit(self, organ: Optional[str] = None, create_issues: bool = False) -> None:
        """Full organ or system health report. With create_issues, file GitHub issues for findings."""
        print(f"\n  Audit Report: {organ or 'FULL SYSTEM'}")
        print("  " + "=" * 50)

        organs_to_check = {}
        if organ:
            key = resolve_organ_key(organ)
            organ_data = self.registry.get("organs", {}).get(key, {})
            if organ_data:
                organs_to_check[key] = organ_data
            else:
                raise GovernanceError(f"Organ '{organ}' not found in registry.")
        else:
            organs_to_check = self.registry.get("organs", {})

        for organ_key, organ_data in organs_to_check.items():
            repos = organ_data.get("repositories", [])
            total = len(repos)

            statuses = Counter(r.get("promotion_status", "UNKNOWN") for r in repos)
            tiers = Counter(r.get("tier", "unknown") for r in repos)
            impl = Counter(r.get("implementation_status", "UNKNOWN") for r in repos)

            missing_readme = [r["name"] for r in repos if r.get("documentation_status", "").upper() == "EMPTY"]
            missing_ci = [r["name"] for r in repos if not r.get("ci_workflow")]

            print(f"\n  [{organ_short(organ_key)}] {organ_data.get('name', organ_key)} -- {total} repos")
            print(f"  {'---' * 17}")

            print(f"  Promotion: " + ", ".join(f"{s}={c}" for s, c in sorted(statuses.items())))
            print(f"  Tiers:     " + ", ".join(f"{t}={c}" for t, c in sorted(tiers.items())))
            print(f"  Impl:      " + ", ".join(f"{i}={c}" for i, c in sorted(impl.items())))

            if missing_readme:
                print(f"\n  CRITICAL: {len(missing_readme)} repos missing README:")
                for name in missing_readme[:5]:
                    print(f"    - {name}")

            if missing_ci:
                print(f"\n  WARNING: {len(missing_ci)} repos without CI:")
                for name in missing_ci[:5]:
                    print(f"    - {name}")

            cand = statuses.get("CANDIDATE", 0)
            if cand > MAX_CANDIDATE_PER_ORGAN:
                print(f"\n  WIP VIOLATION: {cand} CANDIDATE (limit {MAX_CANDIDATE_PER_ORGAN})")

            recs = []
            if cand > MAX_CANDIDATE_PER_ORGAN:
                recs.append(f"Triage CANDIDATE repos: promote {cand - MAX_CANDIDATE_PER_ORGAN}+ to PUBLIC_PROCESS or archive")
            if missing_ci:
                recs.append(f"Add CI workflows to {len(missing_ci)} repos")
            if statuses.get("LOCAL", 0) > 0:
                recs.append(f"Evaluate {statuses['LOCAL']} LOCAL repos for CANDIDATE promotion")
            if not recs:
                recs.append("Organ is healthy -- no immediate action needed")

            print(f"\n  Recommendations:")
            for r in recs:
                print(f"    -> {r}")

            if create_issues and recs and recs[0] != "Organ is healthy -- no immediate action needed":
                self._create_audit_issues(organ_key, recs)

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
