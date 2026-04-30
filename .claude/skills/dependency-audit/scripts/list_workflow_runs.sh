#!/usr/bin/env bash
# List the 5 most recent runs of a specific workflow on claude/ci-demo.
# Output is JSON: array of {url, status, conclusion}. The Skill body parses
# this to populate `workflow_runs` in its final response.
#
# Usage: list_workflow_runs.sh <workflow-filename>
#   e.g. list_workflow_runs.sh lint-and-test.yml
set -euo pipefail

WORKFLOW="${1:?Usage: list_workflow_runs.sh <workflow-filename>}"
gh run list \
    --branch claude/ci-demo \
    --limit 5 \
    --workflow="$WORKFLOW" \
    --json url,status,conclusion
