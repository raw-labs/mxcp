#!/bin/bash
# Simple wrapper for the PyPI publishing script

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Change to project root
cd "$PROJECT_ROOT"

# Run the Python script with all arguments passed through
python scripts/publish.py "$@" 