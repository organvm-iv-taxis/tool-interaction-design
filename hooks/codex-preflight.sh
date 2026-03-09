#!/usr/bin/env bash
# Conductor preflight for non-Claude agents (Codex, Gemini, OpenCode, etc.)
# Source this in .zshrc: source ~/Workspace/organvm-iv-taxis/tool-interaction-design/hooks/codex-preflight.sh
#
# Usage:
#   conductor-preflight          # auto-detects agent as "unknown"
#   conductor-preflight codex    # explicit agent identity
#   conductor-preflight gemini

CONDUCTOR_BASE="/Users/4jp/Workspace/organvm-iv-taxis/tool-interaction-design"

conductor-preflight() {
  local agent="${1:-unknown}"
  local venv="$CONDUCTOR_BASE/.venv/bin/python3"

  if [[ ! -x "$venv" ]]; then
    echo "[CONDUCTOR] Preflight unavailable — no venv at $venv"
    return 1
  fi

  "$venv" -m conductor preflight --agent "$agent" --cwd "$PWD"
}
