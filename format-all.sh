#!/bin/bash

# Auto-format script for MXCP

echo "🔧 Running auto-formatters for MXCP..."
echo ""

echo "📦 Formatting MXCP..."
uv run python -m ruff check --fix .
uv run python -m black .

echo ""
echo "✅ Project formatted!"
echo "Run ./check-all.sh to verify all checks pass."

