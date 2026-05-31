#!/usr/bin/env bash
# Remind agent to run UI acceptance after sessions that touched site files.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

if git status --porcelain 2>/dev/null | grep -qE '^(M| M|M |A| A|A )?(src/site/|docs/assets/|docs/app/)'; then
  echo '{"followup": "Site files changed. Run: python3 scripts/ui_acceptance.py --quick && update documentation/workflow_state.yaml if needed."}'
fi
