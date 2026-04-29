#!/usr/bin/env bash
# Idempotently switch to claude/ci-demo: track the remote tip if it exists,
# otherwise fork from the current HEAD. Works on first run and subsequent runs
# without force-pushing.
#
# Usage: switch_to_demo_branch.sh
set -euo pipefail
git fetch origin claude/ci-demo 2>/dev/null || true
if git rev-parse --verify origin/claude/ci-demo >/dev/null 2>&1; then
    git checkout -B claude/ci-demo origin/claude/ci-demo
else
    git checkout -B claude/ci-demo
fi
