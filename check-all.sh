#!/bin/bash

# Style check script for MXCP

echo "🔍 Running style checks for MXCP..."
echo ""

# Track failures
FAILED=0

echo "📦 Checking MXCP..."
uv run python -m ruff check . || FAILED=1
uv run python -m black --check --diff . || FAILED=1
uv run python -m mypy . || FAILED=1

echo ""

if [ $FAILED -eq 0 ]; then
    echo "✅ All style checks passed!"
    exit 0
else
    echo "❌ Some style checks failed. Run ./format-all.sh to auto-fix formatting issues."
    exit 1
fi
