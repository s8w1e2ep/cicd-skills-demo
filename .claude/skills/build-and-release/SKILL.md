---
name: build-and-release
description: Set up a GitHub Actions workflow that triggers on git tag pushes matching `v*`, builds the project's distributable artifact (`npm pack` for Node, `python -m build` for Python), and creates a GitHub Release with the artifact attached and auto-generated release notes. Use this skill whenever the user wants release automation, "publish a new version", "tag and ship", "create a GitHub Release whenever I push a tag", "build artifacts on release", "automate the release process", or wants the standard tag-driven release pattern — even if they don't explicitly say "release" or "tag". Do not use for CI testing, dependency CVE scanning, or secret/SAST scanning — defer to the sibling skills for those.
---

# Build-and-release workflow

## What this skill does

Writes (or updates) `.github/workflows/release.yml` in the current repo, commits it to `claude/ci-demo`, and ensures a single PR to the default branch exists. The workflow triggers on any pushed tag matching `v*`, builds the distributable for the detected language stack (`npm pack` → `*.tgz` for Node; `python -m build` → wheel + sdist for Python), and creates a GitHub Release with the artifact attached and auto-generated notes. This skill provisions the workflow only — actual builds and releases happen on the GitHub Actions runner when a tag is pushed.

## Shared scripts

The git/gh operations are shared across all four CI/CD Skills and live under `.claude/scripts/`. The Skill body invokes them rather than inlining the commands so that a fix to the idempotency / PR / branch logic touches one file, not four. Available:

- `.claude/scripts/compare_yaml.sh <a> <b>` — semantic-equal compare; prints `SAME` or `DIFF`
- `.claude/scripts/switch_to_demo_branch.sh` — fetch + checkout `claude/ci-demo`, fork from HEAD if remote missing
- `.claude/scripts/ensure_pr.sh` — print existing PR URL, or create a new PR if none exists
- `.claude/scripts/list_workflow_runs.sh <filename.yml>` — JSON list of last 5 runs for one workflow

## Steps

1. **Detect stacks.** Use Read on the repo root for `package.json` and `pyproject.toml` (also `setup.py`). Note which stacks are present in a `detected_stacks` list.

   If neither Node nor Python is detected, exit with `status: refused` and `refused.reason` like "No supported language stack found at repo root."

2. **Render the new workflow.** Read the matching template(s) from `assets/`:
   - Python only: copy `assets/release.python.yml` verbatim.
   - Node only: copy `assets/release.node.yml` verbatim.
   - Both: read both and emit a single workflow file with both jobs preserved as-is under one `jobs:` map. Keep job names `release-python` and `release-node` so the merged file is deterministic across runs.

   Write the rendered content to `/tmp/new-workflow.yml`.

3. **Read existing target if present.** Use Read on `.github/workflows/release.yml`. If the file does not exist, treat it as DIFF and proceed to step 5 with `status: created`.

4. **Idempotency check.** If the file existed in step 3:

   ```bash
   bash .claude/scripts/compare_yaml.sh .github/workflows/release.yml /tmp/new-workflow.yml
   ```

   If the output is `SAME`:
   - Do not write, do not commit, do not push.
   - Get the previous commit URL: `git log -1 --format="%H" -- .github/workflows/release.yml` and the repo URL via `git config --get remote.origin.url`.
   - Get the existing PR URL via `bash .claude/scripts/ensure_pr.sh`.
   - Emit the JSON output with `status: "no_change"` and stop.

   If the output is `DIFF`, set `status: "updated"` and continue.

5. **Switch to the demo branch.**

   ```bash
   bash .claude/scripts/switch_to_demo_branch.sh
   ```

6. **Write the workflow file.** Ensure `.github/workflows/` exists, then Write the contents of `/tmp/new-workflow.yml` to `.github/workflows/release.yml`.

7. **Commit and push.**

   ```bash
   git add .github/workflows/release.yml
   git commit -m "ci: add release workflow via build-and-release skill"
   git push -u origin claude/ci-demo
   ```

8. **Ensure the PR exists.**

   ```bash
   bash .claude/scripts/ensure_pr.sh
   ```

   Capture the printed URL as `pr_url` for the final JSON.

9. **Read the resulting GitHub Actions runs for this workflow.**

   ```bash
   bash .claude/scripts/list_workflow_runs.sh release.yml
   ```

   Note: this workflow is tag-triggered, so the run list on `claude/ci-demo` will usually be empty until someone pushes a tag. That's expected — populate `workflow_runs` with whatever the command returns (often `[]`), and add a note to that effect (see Output format).

10. **Emit the output JSON.** See "Output format" below.

## Output format

After completing the steps (or on early exit from step 1 or step 4), emit exactly one JSON code block as the final content of your response. Do not add prose after it.

```json
{
  "skill": "build-and-release",
  "status": "created" | "updated" | "no_change" | "refused",
  "branch": "claude/ci-demo",
  "workflow_path": ".github/workflows/release.yml",
  "commit_url": "https://github.com/<owner>/<repo>/commit/<sha>" | null,
  "pr_url": "https://github.com/<owner>/<repo>/pull/<n>" | null,
  "workflow_runs": [
    {"url": "...", "status": "queued|in_progress|completed", "conclusion": null|"success"|"failure"}
  ],
  "detected_stacks": ["node", "python"],
  "notes": "<short sentence; mention if workflow_runs is empty because the workflow is tag-triggered>",
  "refused": null | {"reason": "<reason if status is refused>"}
}
```

Status semantics match the other CI/CD skills (`created`, `updated`, `no_change`, `refused`). The release workflow only runs when a tag matching `v*` is pushed, so an empty `workflow_runs` array on creation is normal and not an error — call this out in `notes` (e.g. `"workflow_runs is empty because release.yml triggers only on v* tag push; push a tag to fire it."`).
