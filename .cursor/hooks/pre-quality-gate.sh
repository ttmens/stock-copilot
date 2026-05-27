#!/usr/bin/env bash
# Pre-commit quality gate: docs SSOT + UI quick acceptance
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

if [[ -f scripts/check_docs_ssot.py ]]; then
  python3 scripts/check_docs_ssot.py --project-root "$ROOT" || exit 1
fi

# Only run UI quick check if site/theme or docs assets changed
if git diff --cached --name-only 2>/dev/null | grep -qE '^(src/site/|docs/assets/|docs/app/|docs/index\.html)'; then
  if [[ -f scripts/ui_acceptance.py ]]; then
    python3 scripts/ui_acceptance.py --quick --project-root "$ROOT" || exit 1
  fi
fi

exit 0
