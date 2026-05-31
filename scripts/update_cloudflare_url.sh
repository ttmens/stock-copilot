#!/usr/bin/env bash
# Extract cloudflared tunnel URL and update config.js + regenerate site
# Usage: Run after restarting cloudflared to get new URL

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG_JS="$PROJECT_ROOT/src/site/app/config.js"

echo "=== Extracting cloudflare tunnel URL ==="
TUNNEL_URL=$(/tmp/cloudflared tunnel --url http://localhost:8000 --no-autoupdate 2>&1 | grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' | head -1)

if [ -z "$TUNNEL_URL" ]; then
    echo "ERROR: Could not extract tunnel URL. Is cloudflared running?"
    exit 1
fi

echo "Tunnel URL: $TUNNEL_URL"

# Update config.js
sed -i "s|https://[a-z0-9-]*\.trycloudflare\.com|$TUNNEL_URL|g" "$CONFIG_JS"
echo "Updated config.js"

# Regenerate site
cd "$PROJECT_ROOT"
python scripts/regenerate_docs_site.py
echo "Site regenerated"

# Git commit
git add -A
git commit -m "chore: update cloudflare tunnel URL to $TUNNEL_URL" 2>/dev/null || echo "No changes to commit"
git push origin main 2>/dev/null || echo "Push skipped"

echo "=== Done! New URL: $TUNNEL_URL ==="
