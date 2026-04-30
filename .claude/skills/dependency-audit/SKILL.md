---
name: dependency-audit
description: Set up a GitHub Actions workflow that scans the repo's dependencies for known CVEs on every push, pull request, and weekly schedule. Detects npm and Python (requirements.txt / pyproject.toml) projects automatically. Use this skill whenever the user wants to check for vulnerable packages, supply-chain security, dependency CVE auditing, "are my packages safe?", "scan for known vulnerabilities in my dependencies", "Dependabot-style audit", or wants the workflow to fail when high-severity advisories are found — even if they don't explicitly say "audit" or "CVE". Do not use for secret scanning, SAST or code-level static analysis, lint/test, or release automation — defer to the sibling skills for those.
---

# Dependency-audit workflow

## What this skill does

Writes (or updates) `.github/workflows/dependency-audit.yml` in the current repo, commits it to `claude/ci-demo`, and ensures a single PR to the default branch exists. The workflow runs `npm audit` for Node projects and `pip-audit` for Python projects; the run fails when high-severity (or above) advisories are found. This skill provisions the workflow only — actual dependency scanning happens on the GitHub Actions runner.

## Scripts

The git/gh operations live under this Skill's own `scripts/` directory. The Skill body invokes them rather than inlining shell commands. Available:

- `.claude/skills/dependency-audit/scripts/compare_yaml.sh <a> <b>` — semantic-equal compare; prints `SAME` or `DIFF`
- `.claude/skills/dependency-audit/scripts/switch_to_demo_branch.sh` — fetch + checkout `claude/ci-demo`, fork from HEAD if remote missing
- `.claude/skills/dependency-audit/scripts/ensure_pr.sh` — print existing PR URL, or create a new PR if none exists
- `.claude/skills/dependency-audit/scripts/list_workflow_runs.sh <filename.yml>` — JSON list of last 5 runs for one workflow

## Steps

1. **Detect stacks.** Use Read on the repo root for `package.json` and `pyproject.toml` (also `requirements.txt`, `setup.py`). Note which stacks are present in a `detected_stacks` list.

   If neither Node nor Python is detected, exit with `status: refused` and a `refused.reason` like "No supported language stack found at repo root."

2. **Render the new workflow.** Read the matching template(s) from `assets/`:
   - Python only: copy `assets/dependency-audit.python.yml` verbatim.
   - Node only: copy `assets/dependency-audit.node.yml` verbatim.
   - Both: read both and emit a single workflow file with both jobs preserved as-is under one `jobs:` map. Keep job names `python` and `node` so the merged file is deterministic across runs.

   Write the rendered content to `/tmp/new-workflow.yml`.

3. **Read existing target if present.** Use Read on `.github/workflows/dependency-audit.yml`. If the file does not exist, treat it as DIFF and proceed to step 5 with `status: created`.

4. **Idempotency check.** If the file existed in step 3:

   ```bash
   bash .claude/skills/dependency-audit/scripts/compare_yaml.sh .github/workflows/dependency-audit.yml /tmp/new-workflow.yml
   ```

   If the output is `SAME`:
   - Do not write, do not commit, do not push.
   - Get the previous commit URL: `git log -1 --format="%H" -- .github/workflows/dependency-audit.yml` and the repo URL via `git config --get remote.origin.url`.
   - Get the existing PR URL via `bash .claude/skills/dependency-audit/scripts/ensure_pr.sh`.
   - Emit the JSON output with `status: "no_change"` and stop.

   If the output is `DIFF`, set `status: "updated"` and continue.

5. **Switch to the demo branch.**

   ```bash
   bash .claude/skills/dependency-audit/scripts/switch_to_demo_branch.sh
   ```

6. **Write the workflow file.** Ensure `.github/workflows/` exists, then Write the contents of `/tmp/new-workflow.yml` to `.github/workflows/dependency-audit.yml`.

7. **Commit and push.**

   ```bash
   git add .github/workflows/dependency-audit.yml
   git commit -m "ci: add dependency-audit workflow via dependency-audit skill"
   git push -u origin claude/ci-demo
   ```

8. **Ensure the PR exists.**

   ```bash
   bash .claude/skills/dependency-audit/scripts/ensure_pr.sh
   ```

   Capture the printed URL as `pr_url` for the final JSON.

9. **Read the resulting GitHub Actions runs.**

   ```bash
   bash .claude/skills/dependency-audit/scripts/list_workflow_runs.sh dependency-audit.yml
   ```

   Parse the JSON output to populate `workflow_runs`.

10. **Emit the output JSON.** See "Output format" below.

## Output format

After completing the steps (or on early exit from step 1 or step 4), emit exactly one JSON code block as the final content of your response. Do not add prose after it. The server parses the last JSON block from your output.

```json
{
  "skill": "dependency-audit",
  "status": "created" | "updated" | "no_change" | "refused",
  "branch": "claude/ci-demo",
  "workflow_path": ".github/workflows/dependency-audit.yml",
  "commit_url": "https://github.com/<owner>/<repo>/commit/<sha>" | null,
  "pr_url": "https://github.com/<owner>/<repo>/pull/<n>" | null,
  "workflow_runs": [
    {"url": "...", "status": "queued|in_progress|completed", "conclusion": null|"success"|"failure"}
  ],
  "detected_stacks": ["node", "python"],
  "notes": "<one short sentence — caveats, assumptions, or empty>",
  "refused": null | {"reason": "<reason if status is refused>"}
}
```

Status semantics:

- `created`: the workflow file did not exist; you wrote it for the first time.
- `updated`: file existed but new content differs semantically; commit pushed.
- `no_change`: file exists and is semantically equal to the rendered template; you did not commit. `commit_url` is the previous commit (looked up via `git log` in step 4).
- `refused`: preconditions not met (e.g. neither Node nor Python detected). Do not commit. Populate `refused.reason`.
