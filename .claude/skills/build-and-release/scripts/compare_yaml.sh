#!/usr/bin/env bash
# Semantic YAML compare: prints SAME if both files parse to equal dicts, else DIFF.
#
# Used by every CI/CD Skill's idempotency check (step 4) so re-running with the
# same input doesn't re-commit. We compare parsed structure, not bytes, so
# whitespace/comment churn between runs doesn't trigger false "updated".
#
# Usage: compare_yaml.sh <existing-yaml> <new-yaml>
set -euo pipefail
python3 -c '
import sys, yaml
a = yaml.safe_load(open(sys.argv[1]))
b = yaml.safe_load(open(sys.argv[2]))
print("SAME" if a == b else "DIFF")
' "$1" "$2"
