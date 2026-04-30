#!/usr/bin/env bash
# Idempotently switch to the demo branch: track the remote tip if it exists,
# otherwise fork from the current HEAD. Works on first run and subsequent runs
# without force-pushing.
#
# Branch name comes from the DEMO_BRANCH env var so the orchestrator can pass
# a per-pipeline-run name (e.g. demo-20260430-a3f8b2) and avoid collisions
# across concurrent sessions. Falls back to claude/ci-demo when unset, which
# preserves the original single-shared-branch behaviour for the legacy
# /run/skill/{name} path.
#
# Usage: switch_to_demo_branch.sh
set -euo pipefail
BRANCH="${DEMO_BRANCH:-claude/ci-demo}"
git fetch origin "$BRANCH" 2>/dev/null || true
if git rev-parse --verify "origin/$BRANCH" >/dev/null 2>&1; then
    git checkout -B "$BRANCH" "origin/$BRANCH"
else
    git checkout -B "$BRANCH"
fi
