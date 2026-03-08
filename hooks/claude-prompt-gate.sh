#!/usr/bin/env bash
# Conductor phase-awareness hook for Claude Code user-prompt-submit
# Reads .conductor/session.json and emits phase context as a one-liner.
set -euo pipefail

SESSION_FILE="/Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design/.conductor/session.json"

if [[ ! -f "$SESSION_FILE" ]]; then
    echo "[CONDUCTOR] No active session. Start one: conductor_session_start(organ, repo, scope)"
    exit 0
fi

# Fast JSON parse with python3 (available on macOS, no deps)
python3 -c "
import json, sys, time
try:
    s = json.load(open('$SESSION_FILE'))
    phase = s.get('current_phase', '?')
    organ = s.get('organ', '?')
    repo = s.get('repo', '?')
    elapsed = int((time.time() - s.get('start_time', time.time())) / 60)
    print(f'[CONDUCTOR] Phase: {phase} | {organ}/{repo} | {elapsed}min elapsed')

    # Gate check: warn if prompt suggests implementation but phase is FRAME/SHAPE
    prompt = sys.stdin.read().lower() if not sys.stdin.isatty() else ''
    impl_keywords = ['implement', 'write code', 'create file', 'add function', 'build', 'fix bug', 'refactor']
    if phase in ('FRAME', 'SHAPE') and any(kw in prompt for kw in impl_keywords):
        print(f'[GATE] You are in {phase} phase. Transition to BUILD before implementing.')

    # Directive prefix detection: ingest:, research:, capture:, distill:
    directive_prefixes = {
        'ingest:': 'INGEST',
        'research:': 'RESEARCH',
        'capture:': 'CAPTURE',
        'distill:': 'DISTILL',
    }
    stripped = prompt.strip()
    for prefix, directive_type in directive_prefixes.items():
        if stripped.startswith(prefix):
            print(f'[DIRECTIVE:{directive_type}] Route through conductor_{prefix.rstrip(\":\")} tool.')
            break
except Exception as e:
    print(f'[CONDUCTOR] Session read error: {e}')
" 2>/dev/null
