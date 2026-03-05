"""Guardian Angel — wisdom-enriched advisory engine wrapping the Oracle.

Composes Oracle detectors with the WisdomCorpus to provide:
  - counsel:    Enhanced consult with wisdom enrichment + mastery tracking
  - whisper:    Lightweight ambient guidance for specific actions
  - teach:      On-demand pedagogical lookup of a principle
  - landscape:  Risk-reward mapping for a decision
  - growth_report: Full mastery and growth trajectory
"""

from __future__ import annotations

from typing import Any

from .oracle import Advisory, Oracle, OracleContext
from .wisdom import WisdomCorpus, WisdomEntry


class GuardianAngel:
    """Wisdom-enriched advisory engine composing Oracle + WisdomCorpus."""

    def __init__(self, oracle: Oracle | None = None) -> None:
        self.oracle = oracle or Oracle()
        self.corpus = WisdomCorpus()

    # ------------------------------------------------------------------
    # counsel — enhanced consult
    # ------------------------------------------------------------------

    def counsel(
        self,
        context: dict[str, Any] | OracleContext | None = None,
        *,
        max_advisories: int = 8,
        include_wisdom: bool = True,
        gate_mode: bool = False,
    ) -> list[Advisory]:
        """Enhanced consult: Oracle detectors + wisdom enrichment + mastery tracking.

        1. Calls oracle.consult() for all detector advisories.
        2. Enriches advisories that have wisdom_id with corpus data.
        3. Optionally adds 1-2 standalone wisdom advisories from corpus.
        4. Skips wisdom already internalized (mastery ledger check).
        5. Records wisdom shown (mastery tracking).
        6. Returns combined, sorted advisory list.
        """
        # Get base advisories from Oracle
        advisories = self.oracle.consult(
            context,
            max_advisories=max_advisories + 3,  # request extra, we'll trim
            include_narrative=True,
            gate_mode=gate_mode,
        )

        if not include_wisdom:
            return advisories[:max_advisories]

        # Normalize context for phase info
        ctx = self._normalize_context(context)

        # Enrich advisories that already have wisdom_id
        for adv in advisories:
            if adv.wisdom_id:
                entry = self.corpus.get_by_id(adv.wisdom_id)
                if entry and not adv.teaching:
                    adv.teaching = entry.teaching
                if entry and not adv.narrative:
                    adv.narrative = entry.metaphor[:200]

        # Add standalone wisdom advisory (phase-relevant, not internalized)
        wisdom_added = sum(1 for a in advisories if a.wisdom_id)
        if wisdom_added < 2:
            standalone = self._generate_standalone_wisdom(ctx)
            advisories.extend(standalone)

        # Record wisdom shown and add mastery notes
        for adv in advisories:
            if adv.wisdom_id:
                self.oracle._record_wisdom_shown(adv.wisdom_id)
                mastery = self.oracle._load_mastery()
                enc = mastery.get("encountered", {}).get(adv.wisdom_id, {})
                times = enc.get("times_shown", 0)
                if times > 1 and not adv.mastery_note:
                    adv.mastery_note = f"You've encountered this principle {times} times."

        # Sort and trim
        advisories.sort(key=lambda a: a.sort_key())
        return advisories[:max_advisories]

    # ------------------------------------------------------------------
    # whisper — lightweight ambient guidance
    # ------------------------------------------------------------------

    def whisper(
        self,
        action_description: str,
        context: dict[str, Any] | OracleContext | None = None,
    ) -> Advisory | None:
        """Lightweight ambient guidance — returns None if no warning needed.

        Checks the action description against wisdom triggers for fast,
        contextual micro-advice. Designed to be called frequently.
        """
        if not action_description:
            return None

        ctx = self._normalize_context(context)

        # Derive triggers from the action description
        triggers = self._extract_triggers(action_description)
        if not triggers:
            return None

        # Query corpus for matching wisdom
        entries = self.corpus.query(
            triggers=triggers,
            phase=ctx.current_phase or None,
            limit=3,
        )

        if not entries:
            return None

        # Pick the best match that isn't already internalized
        for entry in entries:
            if self.oracle._check_internalization(entry.id):
                continue

            self.oracle._record_wisdom_shown(entry.id)
            return Advisory(
                category="wisdom",
                severity=entry.severity_hint,
                message=f"{entry.principle}: {entry.summary}",
                recommendation=entry.teaching[:200],
                detector="guardian_whisper",
                wisdom_id=entry.id,
                teaching=entry.teaching,
                narrative=entry.metaphor[:200],
                confidence=0.6,
                tags=["wisdom", "whisper"] + entry.tags[:3],
            )

        return None

    # ------------------------------------------------------------------
    # teach — on-demand pedagogical lookup
    # ------------------------------------------------------------------

    def teach(self, topic: str) -> dict[str, Any]:
        """On-demand: look up a principle, explain pedagogically, show history.

        Returns a dict with principle details + user's mastery history.
        """
        # Try exact ID match first
        entry = self.corpus.get_by_id(topic)

        # Fall back to search
        if not entry:
            results = self.corpus.search(topic)
            if results:
                entry = results[0]

        if not entry:
            return {
                "found": False,
                "query": topic,
                "suggestion": "Try searching for: SOLID, TDD, MVP, Scylla, etc.",
                "available_count": self.corpus.count,
            }

        # Get mastery history for this entry
        mastery = self.oracle._load_mastery()
        encountered = mastery.get("encountered", {}).get(entry.id, {})
        internalized = entry.id in mastery.get("internalized", {})

        return {
            "found": True,
            "principle": entry.principle,
            "domain": entry.domain,
            "summary": entry.summary,
            "teaching": entry.teaching,
            "metaphor": entry.metaphor,
            "phase_relevance": entry.phase_relevance,
            "tags": entry.tags,
            "mastery": {
                "times_encountered": encountered.get("times_shown", 0),
                "first_seen": encountered.get("first_seen", ""),
                "last_seen": encountered.get("last_shown", ""),
                "internalized": internalized,
            },
            "related": [
                {"id": r.id, "principle": r.principle}
                for r in self.corpus.query(
                    tags=entry.tags[:2],
                    domain=entry.domain,
                    limit=3,
                )
                if r.id != entry.id
            ],
        }

    # ------------------------------------------------------------------
    # landscape — risk-reward mapping
    # ------------------------------------------------------------------

    def landscape(
        self,
        decision: str,
        context: dict[str, Any] | OracleContext | None = None,
    ) -> dict[str, Any]:
        """Map risk-reward poles for a decision with personalized positioning.

        Returns poles (extremes), wisdom entries, and profile-based positioning.
        """
        ctx = self._normalize_context(context)
        triggers = self._extract_triggers(decision)

        # Find relevant wisdom for this decision
        wisdom_entries = self.corpus.query(
            triggers=triggers,
            phase=ctx.current_phase or None,
            limit=5,
        )

        # Build poles based on detected tensions
        poles = self._identify_poles(decision, triggers)

        # Profile-based positioning
        report = self.oracle.get_mastery_report()
        profile = self.oracle.build_profile()

        positioning = {
            "risk_appetite": profile.risk_appetite,
            "ship_rate": profile.ship_rate,
            "cadence": profile.cadence,
        }

        return {
            "decision": decision,
            "poles": poles,
            "wisdom": [
                {
                    "id": e.id,
                    "principle": e.principle,
                    "summary": e.summary,
                    "teaching": e.teaching,
                    "relevance": "high" if any(t in e.triggers for t in triggers) else "moderate",
                }
                for e in wisdom_entries
            ],
            "positioning": positioning,
            "mastery_context": {
                "score": report.get("mastery_score", 0.0),
                "velocity": report.get("learning_velocity", "starting"),
            },
        }

    # ------------------------------------------------------------------
    # growth_report — full mastery and growth trajectory
    # ------------------------------------------------------------------

    def growth_report(self) -> dict[str, Any]:
        """Full growth report: mastered, practicing, trajectory."""
        report = self.oracle.get_mastery_report()

        # Enrich growth areas with wisdom details
        enriched_areas = []
        for wid in report.get("top_growth_areas", []):
            entry = self.corpus.get_by_id(wid)
            if entry:
                enriched_areas.append({
                    "id": wid,
                    "principle": entry.principle,
                    "domain": entry.domain,
                    "summary": entry.summary,
                })
            else:
                enriched_areas.append({"id": wid})

        # Enrich recently internalized
        enriched_internalized = []
        for item in report.get("recently_internalized", []):
            entry = self.corpus.get_by_id(item["id"])
            enriched_internalized.append({
                **item,
                "principle": entry.principle if entry else item["id"],
            })

        report["top_growth_areas"] = enriched_areas
        report["recently_internalized"] = enriched_internalized
        report["corpus_size"] = self.corpus.count
        report["corpus_domains"] = self.corpus.domains

        return report

    # ------------------------------------------------------------------
    # corpus_search — browse/search the wisdom corpus
    # ------------------------------------------------------------------

    def corpus_search(self, query: str | None = None) -> dict[str, Any]:
        """Browse or search the wisdom corpus."""
        if query:
            results = self.corpus.search(query)
            return {
                "query": query,
                "count": len(results),
                "results": [
                    {
                        "id": e.id,
                        "principle": e.principle,
                        "domain": e.domain,
                        "summary": e.summary,
                    }
                    for e in results
                ],
            }

        # No query — return corpus overview
        return {
            "total_entries": self.corpus.count,
            "domains": self.corpus.domains,
            "by_domain": {
                domain: len(self.corpus.query(domain=domain, limit=100))
                for domain in self.corpus.domains
            },
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_context(
        context: dict[str, Any] | OracleContext | None,
    ) -> OracleContext:
        if context is None:
            return OracleContext()
        if isinstance(context, OracleContext):
            return context
        if isinstance(context, dict):
            return OracleContext.from_dict(context)
        return OracleContext()

    @staticmethod
    def _extract_triggers(text: str) -> list[str]:
        """Derive wisdom triggers from free-text action/decision description."""
        text_lower = text.lower()
        trigger_keywords = {
            "test": ["tdd", "testing", "test_first"],
            "refactor": ["refactoring", "code_quality", "simplification"],
            "ship": ["shipping", "fear_of_shipping", "perfectionism"],
            "scope": ["scope_complex", "scope_creep", "feature_creep"],
            "deploy": ["deployment", "ci_cd", "release"],
            "rewrite": ["rewrite", "ambitious_rewrite", "second_system"],
            "api": ["api_design", "interface_design"],
            "debt": ["tech_debt", "shortcut", "quick_hack"],
            "complex": ["complexity_trap", "over_engineering", "simplification"],
            "mvp": ["mvp", "minimum_viable", "over_building"],
            "perfect": ["perfectionism", "fear_of_shipping", "wabi_sabi"],
            "stuck": ["analysis_paralysis", "stuck_project", "planning_paralysis"],
            "risk": ["risky_decision", "risk_assessment"],
            "security": ["security", "vulnerability", "threat_model"],
            "design": ["system_design", "architecture", "interface_design"],
            "database": ["database_design", "schema", "migration"],
            "performance": ["performance", "optimization", "premature_optimization"],
            "dependency": ["dependency", "coupling", "dependency_inversion"],
            "error": ["error_handling", "failure_learning", "resilience"],
            "new": ["new_project", "blank_slate", "new_repo"],
            "launch": ["launch", "delayed_launch", "pre_launch_anxiety"],
            "break": ["burnout", "overwork", "pacing"],
        }

        triggers = []
        for keyword, mapped_triggers in trigger_keywords.items():
            if keyword in text_lower:
                triggers.extend(mapped_triggers)

        return list(set(triggers))

    def _generate_standalone_wisdom(self, ctx: OracleContext) -> list[Advisory]:
        """Generate 1-2 standalone wisdom advisories from corpus."""
        advisories: list[Advisory] = []

        # Get a phase-relevant random insight
        entry = self.corpus.random_insight(ctx.current_phase or None)
        if not entry:
            return advisories

        # Skip if internalized
        if self.oracle._check_internalization(entry.id):
            return advisories

        advisories.append(Advisory(
            category="wisdom",
            severity=entry.severity_hint,
            message=f"{entry.principle}: {entry.summary}",
            recommendation=entry.teaching[:200],
            detector="guardian_wisdom",
            wisdom_id=entry.id,
            teaching=entry.teaching,
            narrative=entry.metaphor[:200],
            confidence=0.5,
            tags=["wisdom", "insight"] + entry.tags[:3],
        ))

        return advisories

    @staticmethod
    def _identify_poles(decision: str, triggers: list[str]) -> list[dict[str, str]]:
        """Identify opposing poles/tensions for a decision."""
        # Map common tensions
        tension_map = {
            "perfectionism": ("Perfection", "Speed", "Polish every detail vs ship fast"),
            "shipping": ("Speed", "Quality", "Ship now vs wait for quality"),
            "scope_complex": ("Ambition", "Focus", "Build everything vs build one thing well"),
            "over_engineering": ("Robustness", "Simplicity", "Handle every case vs keep it simple"),
            "rewrite": ("Fresh Start", "Incremental", "Rewrite from scratch vs evolve existing"),
            "tech_debt": ("Speed Now", "Sustainability", "Quick hack vs proper solution"),
            "risk_assessment": ("Boldness", "Caution", "Take the leap vs wait for certainty"),
            "tdd": ("Coverage", "Velocity", "Test everything vs ship features"),
            "security": ("Security", "Usability", "Lock it down vs make it easy"),
            "mvp": ("Completeness", "Learning", "Build the vision vs test the hypothesis"),
        }

        poles = []
        for trigger in triggers:
            if trigger in tension_map:
                left, right, desc = tension_map[trigger]
                poles.append({
                    "left": left,
                    "right": right,
                    "description": desc,
                    "trigger": trigger,
                })

        # Default tension if nothing matched
        if not poles:
            poles.append({
                "left": "Action",
                "right": "Deliberation",
                "description": "Act now with imperfect information vs gather more context",
                "trigger": "default",
            })

        return poles
