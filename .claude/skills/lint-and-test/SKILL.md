---
name: lint-and-test
description: Set up a GitHub Actions workflow that runs lint and unit tests on every push and pull request, for a Node or Python repo. Detects the language stack from package.json / pyproject.toml automatically. Use this skill whenever the user wants CI for tests, linting, type-checking, code style enforcement, build verification, or "make sure the tests pass before merge" — even if they don't explicitly say "workflow" or "GitHub Actions". Do not use for dependency CVE scanning, secret scanning, or release automation — defer to the sibling skills for those.
---

# Lint and test workflow

## What this skill does

Writes (or updates) `.github/workflows/lint-and-test.yml` in the current repo, commits it to the demo branch, and ensures a single PR to the default branch exists. The demo branch defaults to `claude/ci-demo` but the orchestrator can override it via the `DEMO_BRANCH` env var (so each pipeline run can use a fresh branch). The actual lint and test execution happens on the GitHub Actions runner — this skill only provisions the workflow file.

## Scripts

The git/gh operations live under this Skill's own `scripts/` directory. The Skill body invokes them rather than inlining shell commands. Available:

- `.claude/skills/lint-and-test/scripts/compare_yaml.sh <a> <b>` — semantic-equal compare; prints `SAME` or `DIFF`
- `.claude/skills/lint-and-test/scripts/switch_to_demo_branch.sh` — fetch + checkout the demo branch (`$DEMO_BRANCH`, default `claude/ci-demo`), fork from HEAD if remote missing
- `.claude/skills/lint-and-test/scripts/ensure_pr.sh` — print existing PR URL, or create a new PR if none exists
- `.claude/skills/lint-and-test/scripts/list_workflow_runs.sh <filename.yml>` — JSON list of last 5 runs for one workflow

## Steps

Follow these in order. The semantic compare in step 4 is the idempotency gate: if it returns `SAME`, exit with `no_change` and do not modify anything.

1. **Detect stacks.** Use Read on the repo root for `package.json` and `pyproject.toml` (also check `requirements.txt`, `setup.py` as fallbacks). Note which stacks are present in a `detected_stacks` list.

   If neither Node nor Python is detected, exit with `status: refused` and a `refused.reason` like "No supported language stack found at repo root."

2. **Render the new workflow.** Read the matching template(s) from `assets/`:
   - Python only: copy `assets/lint-and-test.python.yml` verbatim.
   - Node only: copy `assets/lint-and-test.node.yml` verbatim.
   - Both: read both, write a single workflow file with both jobs preserved as-is under one `jobs:` map. Job names must remain `python` and `node` so the merged file is deterministic.

   Write the rendered content to `/tmp/new-workflow.yml`.

3. **Read existing target if present.** Use Read on `.github/workflows/lint-and-test.yml`. If the file does not exist, treat it as DIFF and proceed to step 5 with `status: created`.

4. **Idempotency check.** If the file existed in step 3:

   ```bash
   bash .claude/skills/lint-and-test/scripts/compare_yaml.sh .github/workflows/lint-and-test.yml /tmp/new-workflow.yml
   ```

   If the output is `SAME`:
   - Do not write, do not commit, do not push.
   - Get the previous commit URL: `git log -1 --format="%H" -- .github/workflows/lint-and-test.yml` and combine with the repo URL from `git config --get remote.origin.url` (strip `.git`, convert SSH to HTTPS if needed).
   - Get the existing PR URL via `bash .claude/skills/lint-and-test/scripts/ensure_pr.sh` (it prints the existing URL; never creates a duplicate).
   - Emit the JSON output with `status: "no_change"` and stop.

   If the output is `DIFF`, set `status: "updated"` and continue.

5. **Switch to the demo branch.**

   ```bash
   bash .claude/skills/lint-and-test/scripts/switch_to_demo_branch.sh
   ```

6. **Write the workflow file.** Ensure `.github/workflows/` exists, then Write the contents of `/tmp/new-workflow.yml` to `.github/workflows/lint-and-test.yml`.

7. **Commit and push.** Push to whatever branch the previous step checked out — use `git push -u origin "$(git branch --show-current)"` so per-pipeline branch names work without hardcoding.

   ```bash
   git add .github/workflows/lint-and-test.yml
   git commit -m "ci: add lint-and-test workflow via lint-and-test skill"
   git push -u origin "$(git branch --show-current)"
   ```

8. **Ensure the PR exists.**

   ```bash
   bash .claude/skills/lint-and-test/scripts/ensure_pr.sh
   ```

   Capture the printed URL as `pr_url` for the final JSON.

9. **Read the resulting GitHub Actions runs.**

   ```bash
   bash .claude/skills/lint-and-test/scripts/list_workflow_runs.sh lint-and-test.yml
   ```

   Parse the JSON output to populate `workflow_runs`. If the workflow was just pushed, runs may be in `queued` or `in_progress` state — that is fine.

10. **Emit the output JSON.** See "Output format" below.

## Output format

After completing the steps (or on early exit from step 1 or step 4), emit exactly one JSON code block as the final content of your response. Do not add prose after it. The server parses the last JSON block from your output.

```json
{
  "skill": "lint-and-test",
  "status": "created" | "updated" | "no_change" | "refused",
  "branch": "<the actual branch you committed to — get it from `git branch --show-current` after the switch script runs; do NOT hardcode 'claude/ci-demo'>",
  "workflow_path": ".github/workflows/lint-and-test.yml",
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

Example for the no-change case (branch name is illustrative — yours will be whatever `git branch --show-current` returns after step 5):

```json
{
  "skill": "lint-and-test",
  "status": "no_change",
  "branch": "demo-20260430-a3f8b2",
  "workflow_path": ".github/workflows/lint-and-test.yml",
  "commit_url": "https://github.com/foo/bar/commit/abc123",
  "pr_url": "https://github.com/foo/bar/pull/1",
  "workflow_runs": [],
  "detected_stacks": ["python"],
  "notes": "Workflow already up to date.",
  "refused": null
}
```
