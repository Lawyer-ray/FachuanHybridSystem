#!/usr/bin/env bash
# changed_files.sh — Compute changed Python files for CI and local checks.
#
# Usage:
#   ./devtools/changed_files.sh [BASE_REF]
#
# If BASE_REF is not provided:
#   - In CI (GITHUB_BASE_REF set): use $GITHUB_BASE_REF (merge-base for PRs)
#   - Otherwise: try upstream branch, then HEAD~1, then "main"
#
# Output: one changed .py file per line, relative to backend/ root,
#         with the "apps/" prefix stripped (for ruff/mypy consumption).

set -euo pipefail

BASE="${1:-}"

if [ -z "$BASE" ]; then
    if [ -n "${GITHUB_BASE_REF:-}" ]; then
        # CI: use the merge base of the PR
        BASE="origin/${GITHUB_BASE_REF}"
    else
        # Local: try upstream, then HEAD~1, then main
        UPSTREAM=$(git rev-parse --abbrev-ref @{u} 2>/dev/null | sed 's|origin/||' || true)
        if [ -n "$UPSTREAM" ] && git rev-parse "$UPSTREAM" &>/dev/null; then
            BASE="$UPSTREAM"
        elif git rev-parse HEAD~1 &>/dev/null; then
            BASE="HEAD~1"
        else
            BASE="main"
        fi
    fi
fi

# If base doesn't exist, try merge-base
if ! git rev-parse "$BASE" &>/dev/null; then
    BASE=$(git merge-base HEAD HEAD~1 2>/dev/null || echo "")
fi

if [ -z "$BASE" ]; then
    echo "ERROR: Cannot determine base ref" >&2
    exit 1
fi

# Compute changed files
CHANGED=$(git diff --name-only --diff-filter=ACMRT "$BASE" HEAD 2>/dev/null | grep -E '^backend/apps/.*\.py$$' | sed 's|^backend/||' || true)

if [ -z "$CHANGED" ]; then
    exit 0
fi

echo "$CHANGED"
