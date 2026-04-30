#!/usr/bin/env bash
# List the 5 most recent runs of a specific workflow on the demo branch.
# Output is JSON: array of {url, status, conclusion}. The Skill body parses
# this to populate `workflow_runs` in its final response.
#
# Branch name comes from DEMO_BRANCH (set by the orchestrator per pipeline
# run). Falls back to claude/ci-demo for backward compat.
#
# Usage: list_workflow_runs.sh <workflow-filename>
#   e.g. list_workflow_runs.sh lint-and-test.yml
set -euo pipefail

WORKFLOW="${1:?Usage: list_workflow_runs.sh <workflow-filename>}"
BRANCH="${DEMO_BRANCH:-claude/ci-demo}"
gh run list \
    --branch "$BRANCH" \
    --limit 5 \
    --workflow="$WORKFLOW" \
    --json url,status,conclusion
