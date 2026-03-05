"""Oracle advisory engine commands."""

from __future__ import annotations

import json
from pathlib import Path

from ..constants import SESSION_STATE_FILE


def handle(args, *, ontology, engine) -> None:
    from ..oracle import Oracle, OracleContext

    oracle = Oracle()

    # Try to get session context
    session_id = ""
    current_phase = ""
    organ = ""
    if SESSION_STATE_FILE.exists():
        try:
            sess = json.loads(SESSION_STATE_FILE.read_text())
            session_id = sess.get("session_id", "")
            current_phase = sess.get("current_phase", "")
            organ = sess.get("organ", "")
        except Exception as exc:
            from ..observability import log_event
            log_event("oracle_cmd.session_load_error", {"error": str(exc)})

    sub = args.oracle_command

    if sub == "consult":
        _consult(args, oracle, session_id, current_phase, organ)
    elif sub == "gate":
        _gate(args, oracle, session_id, current_phase, organ)
    elif sub == "wisdom":
        _wisdom(args, oracle, session_id, current_phase, organ)
    elif sub == "status":
        _status(args, oracle)
    elif sub == "history":
        _history(args, oracle)
    elif sub == "ack":
        _ack(args, oracle)
    elif sub == "profile":
        _profile(args, oracle)
    elif sub == "detectors":
        _detectors(args, oracle)
    elif sub == "trends":
        _trends(args, oracle)
    elif sub == "calibrate":
        _calibrate(args, oracle)
    elif sub == "export":
        _export(args, oracle)
    elif sub == "diagnose":
        _diagnose(args, oracle)
    elif sub == "counsel":
        _counsel(args, session_id, current_phase, organ)
    elif sub == "teach":
        _teach(args)
    elif sub == "landscape":
        _landscape(args, session_id, current_phase, organ)
    elif sub == "whisper":
        _whisper(args, session_id, current_phase, organ)
    elif sub == "mastery":
        _mastery(args)
    elif sub == "corpus":
        _corpus(args)


def _consult(args, oracle, session_id, current_phase, organ) -> None:
    from ..oracle import OracleContext

    ctx = OracleContext(
        trigger="manual",
        session_id=session_id,
        current_phase=current_phase,
        organ=organ,
    )
    advisories = oracle.consult(ctx, include_narrative=True)
    if args.format == "json":
        print(json.dumps([a.to_dict() for a in advisories], indent=2))
    else:
        if not advisories:
            print("  Oracle: No advisories at this time.")
            return
        severity_icons = {"critical": "XX", "warning": "!!", "caution": "! ", "info": "  "}
        print("\n  ORACLE CONSULT")
        print("  " + "-" * 68)
        for adv in advisories:
            icon = severity_icons.get(adv.severity, "  ")
            print(f"  {icon} [{adv.category.upper()}] {adv.message}")
            if adv.narrative:
                print(f"     ~ {adv.narrative}")
            if adv.recommendation:
                print(f"     -> {adv.recommendation}")
            if adv.tools_suggested:
                print(f"     tools: {', '.join(adv.tools_suggested[:4])}")
            conf = f" (confidence: {adv.confidence:.0%})" if adv.confidence < 1.0 else ""
            det = f" [{adv.detector}]" if adv.detector else ""
            print(f"     hash: {adv.advisory_hash()}{det}{conf}")
        print()


def _gate(args, oracle, session_id, current_phase, organ) -> None:
    from ..oracle import OracleContext

    ctx = OracleContext(
        trigger=args.trigger,
        session_id=session_id,
        current_phase=current_phase,
        target_phase=args.target or "",
        promotion_repo=args.repo or "",
        organ=organ,
    )
    advisories = oracle.consult(ctx, gate_mode=True)
    gate_advisories = [a for a in advisories if a.gate_action]
    if args.format == "json":
        print(json.dumps([a.to_dict() for a in gate_advisories], indent=2))
    else:
        if not gate_advisories:
            print("  Oracle gate: All clear — no gate advisories.")
            return
        print("\n  ORACLE GATE CHECK")
        print("  " + "-" * 68)
        for adv in gate_advisories:
            action_icon = {"block": "BLOCK", "warn": "WARN", "approve": "OK"}.get(
                adv.gate_action, "?"
            )
            print(f"  [{action_icon}] {adv.message}")
            if adv.recommendation:
                print(f"     -> {adv.recommendation}")
        print()


def _wisdom(args, oracle, session_id, current_phase, organ) -> None:
    from ..oracle import OracleContext

    ctx = OracleContext(
        trigger="manual",
        session_id=session_id,
        current_phase=current_phase,
        organ=organ,
    )
    advisories = oracle.consult(ctx, max_advisories=3, include_narrative=True)
    narrative_advs = [a for a in advisories if a.narrative]
    if args.format == "json":
        print(json.dumps([a.to_dict() for a in narrative_advs], indent=2))
    else:
        if not narrative_advs:
            print("  The Oracle is silent. Wisdom emerges with practice.")
            return
        print("\n  ORACLE WISDOM")
        print("  " + "-" * 68)
        for adv in narrative_advs:
            print(f"  ~ {adv.narrative}")
        print()


def _status(args, oracle) -> None:
    scores = oracle.get_detector_scores()
    if args.format == "json":
        print(json.dumps(scores, indent=2))
    else:
        if not scores:
            print("  No detector effectiveness data yet. Scores build over sessions.")
            return
        print("\n  DETECTOR EFFECTIVENESS")
        print("  " + "-" * 68)
        print(f"  {'DETECTOR':<30} {'ADVISED':>8} {'SHIPPED':>8} {'RATE':>8}")
        for det, data in sorted(scores.items()):
            total = data.get("total", 0)
            shipped = data.get("shipped", 0)
            rate = f"{shipped / total:.0%}" if total > 0 else "N/A"
            print(f"  {det:<30} {data.get('advised', 0):>8} {shipped:>8} {rate:>8}")
        print()


def _history(args, oracle) -> None:
    entries = oracle.get_advisory_history(limit=args.limit)
    if args.format == "json":
        print(json.dumps(entries, indent=2))
    else:
        if not entries:
            print("  No advisory history yet.")
            return
        print(f"\n  ADVISORY HISTORY (last {len(entries)})")
        print("  " + "-" * 68)
        for entry in reversed(entries):
            ts = entry.get("timestamp", "")[:19]
            sev = entry.get("severity", "?")
            msg = entry.get("message", "")
            det = entry.get("detector", "")
            print(f"  {ts} [{sev:<7}] {det}: {msg}")
        print()


def _ack(args, oracle) -> None:
    if oracle.acknowledge(args.advisory_hash):
        print(f"  Acknowledged: {args.advisory_hash} (will be suppressed)")
    else:
        print(f"  Already acknowledged: {args.advisory_hash}")


def _profile(args, oracle) -> None:
    profile = oracle.build_profile()
    if args.format == "json":
        print(json.dumps(profile.to_dict(), indent=2))
    else:
        print("\n  BEHAVIORAL PROFILE")
        print("  " + "-" * 68)
        print(f"  Sessions:       {profile.total_sessions} ({profile.total_minutes:.0f} total minutes)")
        print(f"  Ship rate:      {profile.ship_rate:.0%}")
        print(f"  Avg duration:   {profile.avg_duration_min:.0f}m")
        print(f"  Streak:         {profile.streak_current} current, {profile.streak_max} max")
        print(f"  Risk appetite:  {profile.risk_appetite}")
        print(f"  Cadence:        {profile.cadence}")
        if profile.preferred_organs:
            print(f"  Top organs:     {', '.join(profile.preferred_organs)}")
        if profile.active_hours:
            print(f"  Peak hours:     {', '.join(str(h) + ':00' for h in profile.active_hours)}")
        if profile.detector_trust:
            print(
                f"  Trusted dets:   "
                f"{', '.join(f'{k}={v:.0%}' for k, v in sorted(profile.detector_trust.items(), key=lambda x: -x[1])[:5])}"
            )
        if profile.last_session_iso:
            print(f"  Last session:   {profile.last_session_iso[:19]}")
        print()


def _detectors(args, oracle) -> None:
    manifest = oracle.get_detector_manifest()
    if args.format == "json":
        print(json.dumps(manifest, indent=2))
    else:
        print(f"\n  DETECTOR MANIFEST ({len(manifest)} detectors)")
        print("  " + "-" * 68)
        print(f"  {'NAME':<28} {'CAT':<12} {'PHASE':<10} {'ON':>3} {'EFF':>8}")
        for d in manifest:
            on = "Y" if d["enabled"] else "N"
            eff = f"{d['effectiveness']:.0%}" if d["effectiveness"] is not None else "N/A"
            print(f"  {d['name']:<28} {d['category']:<12} {d['phase']:<10} {on:>3} {eff:>8}")
        print()


def _trends(args, oracle) -> None:
    summary = oracle.get_trend_summary()
    if args.format == "json":
        print(json.dumps(summary, indent=2))
    else:
        print("\n  TREND SUMMARY")
        print("  " + "-" * 68)
        analyzed = summary.get("sessions_analyzed", 0)
        print(f"  Sessions analyzed: {analyzed}")
        for label in ("last_5", "last_10", "last_20"):
            w = summary.get(label)
            if w:
                print(
                    f"  {label.replace('_', ' ').title()}: "
                    f"ship {w['ship_rate']:.0%} ({w['shipped']}/{w['count']}), "
                    f"avg {w['avg_duration_min']:.0f}m"
                )
        print()


def _calibrate(args, oracle) -> None:
    result = oracle.calibrate_detector(args.detector, action=args.action)
    if "error" in result:
        print(f"  ERROR: {result['error']}")
    else:
        print(f"  Calibrated '{result['calibrated']}' with action '{result['action']}'")


def _export(args, oracle) -> None:
    export = oracle.export_state()
    output_str = json.dumps(export, indent=2)
    if hasattr(args, "output") and args.output:
        args.output.write_text(output_str)
        print(f"  Exported oracle state to {args.output}")
    else:
        print(output_str)


def _diagnose(args, oracle) -> None:
    diag = oracle.diagnose()
    print(f"\n  ORACLE DIAGNOSTICS (ok: {diag['ok']})")
    print("  " + "-" * 68)
    info = diag.get("info", {})
    for k, v in info.items():
        print(f"  {k}: {v}")
    issues = diag.get("issues", [])
    if issues:
        print()
        for issue in issues:
            level = issue["level"].upper()
            print(f"  [{level}] {issue['message']}")
    else:
        print("  No issues detected.")
    print()


# ---------------------------------------------------------------------------
# Guardian Angel handlers
# ---------------------------------------------------------------------------


def _counsel(args, session_id, current_phase, organ) -> None:
    from ..guardian import GuardianAngel
    from ..oracle import OracleContext

    guardian = GuardianAngel()
    ctx = OracleContext(
        trigger="manual",
        session_id=session_id,
        current_phase=current_phase,
        organ=organ,
    )
    advisories = guardian.counsel(ctx)
    if args.format == "json":
        print(json.dumps([a.to_dict() for a in advisories], indent=2))
    else:
        if not advisories:
            print("  Guardian Angel: All clear — no advisories.")
            return
        severity_icons = {"critical": "XX", "warning": "!!", "caution": "! ", "info": "  "}
        print("\n  GUARDIAN ANGEL COUNSEL")
        print("  " + "-" * 68)
        for adv in advisories:
            icon = severity_icons.get(adv.severity, "  ")
            print(f"  {icon} [{adv.category.upper()}] {adv.message}")
            if adv.teaching:
                print(f"     * {adv.teaching[:120]}")
            elif adv.narrative:
                print(f"     ~ {adv.narrative}")
            if adv.recommendation:
                print(f"     -> {adv.recommendation}")
            if adv.mastery_note:
                print(f"     ({adv.mastery_note})")
            if adv.wisdom_id:
                det_info = f" [{adv.detector}]" if adv.detector else ""
                print(f"     ref: {adv.wisdom_id}{det_info}")
        print()


def _teach(args) -> None:
    from ..guardian import GuardianAngel

    guardian = GuardianAngel()
    result = guardian.teach(args.topic)
    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        if not result.get("found"):
            print(f"  No wisdom found for '{args.topic}'.")
            print(f"  {result.get('suggestion', '')}")
            return
        print(f"\n  {result['principle']}")
        print("  " + "-" * 68)
        print(f"  Domain: {result['domain']}")
        print(f"  {result['summary']}")
        print()
        print(f"  Teaching:")
        for line in result["teaching"].split(". "):
            if line.strip():
                print(f"    {line.strip()}.")
        print()
        if result.get("metaphor"):
            print(f"  Metaphor:")
            print(f"    {result['metaphor']}")
            print()
        mastery = result.get("mastery", {})
        if mastery.get("times_encountered"):
            status = "INTERNALIZED" if mastery["internalized"] else "practicing"
            print(f"  Your history: encountered {mastery['times_encountered']}x, status: {status}")
        if result.get("related"):
            print(f"  Related: {', '.join(r['principle'] for r in result['related'])}")
        print()


def _landscape(args, session_id, current_phase, organ) -> None:
    from ..guardian import GuardianAngel
    from ..oracle import OracleContext

    guardian = GuardianAngel()
    ctx = OracleContext(
        trigger="manual",
        session_id=session_id,
        current_phase=current_phase,
        organ=organ,
    )
    result = guardian.landscape(args.decision, ctx)
    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        print(f"\n  RISK-REWARD LANDSCAPE: {result['decision']}")
        print("  " + "-" * 68)
        for pole in result.get("poles", []):
            print(f"  {pole['left']} <---> {pole['right']}")
            print(f"    {pole['description']}")
        pos = result.get("positioning", {})
        if pos:
            print(f"\n  Your positioning:")
            print(f"    Risk appetite: {pos.get('risk_appetite', '?')}")
            print(f"    Ship rate: {pos.get('ship_rate', 0):.0%}")
            print(f"    Cadence: {pos.get('cadence', '?')}")
        wisdom = result.get("wisdom", [])
        if wisdom:
            print(f"\n  Relevant wisdom:")
            for w in wisdom[:3]:
                print(f"    [{w['relevance'].upper()}] {w['principle']}: {w['summary']}")
        print()


def _whisper(args, session_id, current_phase, organ) -> None:
    from ..guardian import GuardianAngel
    from ..oracle import OracleContext

    guardian = GuardianAngel()
    ctx = OracleContext(
        trigger="manual",
        session_id=session_id,
        current_phase=current_phase,
        organ=organ,
    )
    adv = guardian.whisper(args.action, ctx)
    if args.format == "json":
        print(json.dumps(adv.to_dict() if adv else {"whisper": None}, indent=2))
    else:
        if not adv:
            print("  Guardian Angel: No concerns — proceed.")
        else:
            print(f"\n  GUARDIAN WHISPER")
            print("  " + "-" * 68)
            print(f"  {adv.message}")
            if adv.teaching:
                print(f"  * {adv.teaching[:200]}")
            if adv.recommendation:
                print(f"  -> {adv.recommendation}")
            print()


def _mastery(args) -> None:
    from ..guardian import GuardianAngel

    guardian = GuardianAngel()
    report = guardian.growth_report()
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print("\n  MASTERY & GROWTH REPORT")
        print("  " + "-" * 68)
        print(f"  Score:          {report.get('mastery_score', 0):.1%}")
        print(f"  Velocity:       {report.get('learning_velocity', 'starting')}")
        print(f"  Encountered:    {report.get('principles_encountered', 0)} principles")
        print(f"  Internalized:   {report.get('principles_internalized', 0)} principles")
        print(f"  Corpus size:    {report.get('corpus_size', 0)} entries across {', '.join(report.get('corpus_domains', []))}")
        areas = report.get("top_growth_areas", [])
        if areas:
            print(f"\n  Top growth areas:")
            for a in areas[:5]:
                name = a.get("principle", a.get("id", "?"))
                print(f"    - {name}")
        recent = report.get("recently_internalized", [])
        if recent:
            print(f"\n  Recently internalized:")
            for r in recent[:3]:
                print(f"    - {r.get('principle', r['id'])} (at {r.get('at', '?')[:10]})")
        print()


def _corpus(args) -> None:
    from ..guardian import GuardianAngel

    guardian = GuardianAngel()
    search_query = getattr(args, "search", None)
    result = guardian.corpus_search(search_query)
    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        if "results" in result:
            print(f"\n  WISDOM CORPUS SEARCH: '{result['query']}' ({result['count']} results)")
            print("  " + "-" * 68)
            for e in result["results"]:
                print(f"  [{e['domain']:<14}] {e['id']}: {e['principle']}")
                print(f"               {e['summary']}")
        else:
            print(f"\n  WISDOM CORPUS ({result.get('total_entries', 0)} entries)")
            print("  " + "-" * 68)
            for domain, count in result.get("by_domain", {}).items():
                print(f"  {domain:<16} {count} entries")
        print()
