#!/usr/bin/env bash
#
# Publish alibabacloud-mcp-proxy to PyPI.
#
# Usage:
#   ./publish.sh              # publish to production PyPI
#   ./publish.sh --test       # publish to TestPyPI first
#   ./publish.sh --dry-run    # build only, do not upload
#
# Prerequisites:
#   1. pip install build twine
#   2. Configure PyPI credentials via one of:
#      - ~/.pypirc
#      - TWINE_USERNAME / TWINE_PASSWORD env vars
#      - TWINE_USERNAME=__token__  TWINE_PASSWORD=pypi-xxxx  (API token)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
USE_TEST_PYPI=false
DRY_RUN=false

for arg in "$@"; do
    case "$arg" in
        --test)     USE_TEST_PYPI=true ;;
        --dry-run)  DRY_RUN=true ;;
        -h|--help)
            echo "Usage: $0 [--test] [--dry-run]"
            echo "  --test      Upload to TestPyPI instead of production PyPI"
            echo "  --dry-run   Build only, do not upload"
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg"
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Step 1: Check dependencies
# ---------------------------------------------------------------------------
echo "==> Checking build dependencies..."

for cmd in python3 pip; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "Error: '$cmd' is not installed."
        exit 1
    fi
done

python3 -m pip install --quiet --upgrade build twine

# ---------------------------------------------------------------------------
# Step 2: Clean previous builds
# ---------------------------------------------------------------------------
echo "==> Cleaning previous builds..."
rm -rf dist/ build/ src/*.egg-info

# ---------------------------------------------------------------------------
# Step 3: Build
# ---------------------------------------------------------------------------
echo "==> Building package..."
python3 -m build

echo ""
echo "==> Built artifacts:"
ls -lh dist/

# ---------------------------------------------------------------------------
# Step 4: Verify
# ---------------------------------------------------------------------------
echo ""
echo "==> Verifying package with twine..."
python3 -m twine check dist/*

# ---------------------------------------------------------------------------
# Step 5: Upload
# ---------------------------------------------------------------------------
if [ "$DRY_RUN" = true ]; then
    echo ""
    echo "==> Dry run complete. Skipping upload."
    echo "    To upload manually:"
    echo "      python3 -m twine upload dist/*"
    exit 0
fi

echo ""
if [ "$USE_TEST_PYPI" = true ]; then
    echo "==> Uploading to TestPyPI..."
    python3 -m twine upload --repository testpypi dist/*
    echo ""
    echo "==> Done! Install from TestPyPI with:"
    echo "    pip install --index-url https://test.pypi.org/simple/ lazy.alibabacloud-mcp-proxy"
else
    echo "==> Uploading to PyPI..."
    python3 -m twine upload dist/*
    echo ""
    echo "==> Done! Install with:"
    echo "    pip install lazy.alibabacloud-mcp-proxy"
fi
