#!/bin/bash
# ── Shorts Pipeline Runner ────────────────────────────────────────────────────
# TWO modes:
#   ./run_daily.sh          → daemon mode (keeps running 24/7, posts IG automatically)
#   ./run_daily.sh --once   → one-shot morning batch then exit (for testing)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

# Activate virtualenv if present
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

echo "🚀 Shorts pipeline starting from $REPO_DIR"
echo "   Python: $(python --version)"
echo "   Mode: ${1:-daemon}"

if [ "${1:-}" = "--once" ] || [ "${1:-}" = "--now" ]; then
    # One-shot: run morning batch then pump IG once and exit
    echo "▶ Running one-shot morning batch..."
    python -m pipeline.main --now
    echo "▶ Pumping IG queue..."
    python -m pipeline.main --ig
    echo "✅ One-shot complete."
else
    # Daemon mode: scheduler handles all batches + IG pump every 15 min
    echo "▶ Starting daemon (Ctrl+C to stop)..."
    exec python -m pipeline.main
fi
