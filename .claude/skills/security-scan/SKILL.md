---
name: security-scan
description: Set up a GitHub Actions workflow that performs static security analysis on the repo — gitleaks for leaked secrets and semgrep for SAST (static application security testing) — running on every push, pull request, and weekly schedule, with results uploaded to the GitHub Security tab as SARIF. Use this skill whenever the user wants secret scanning, code-level static analysis, "look for vulnerabilities in my code", "check for leaked credentials or API keys", "is my code safe / secure", "SAST", "code scanning", or generally wants security review baked into CI — even if they don't explicitly say "gitleaks" or "semgrep". Do not use for dependency CVE scanning (that's a different concern — known vulnerabilities in installed packages, not patterns in your own code) or for lint/test or release workflows — defer to the sibling skills for those.
---

# Security-scan workflow

## What this skill does

Writes (or updates) `.github/workflows/security-scan.yml` in the current repo, commits it to `claude/ci-demo`, and ensures a single PR to the default branch exists. The workflow runs gitleaks (secret detection across the full git history) and semgrep (SAST with the auto rule pack) and uploads SARIF to GitHub's Security tab. This skill provisions the workflow only — actual scanning happens on the GitHub Actions runner.

The workflow is language-agnostic — semgrep auto-detects what's in the repo, gitleaks pattern-matches independent of language. There is no per-stack template branching here.

## Scripts

The git/gh operations live under this Skill's own `scripts/` directory. The Skill body invokes them rather than inlining shell commands. Available:

- `.claude/skills/security-scan/scripts/compare_yaml.sh <a> <b>` — semantic-equal compare; prints `SAME` or `DIFF`
- `.claude/skills/security-scan/scripts/switch_to_demo_branch.sh` — fetch + checkout `claude/ci-demo`, fork from HEAD if remote missing
- `.claude/skills/security-scan/scripts/ensure_pr.sh` — print existing PR URL, or create a new PR if none exists
- `.claude/skills/security-scan/scripts/list_workflow_runs.sh <filename.yml>` — JSON list of last 5 runs for one workflow

## Steps

1. **Detect repo presence.** Use Read on the repo root to confirm there is at least one source file or a `.git` directory implied by being on a checkout. If the cwd is empty, exit with `status: refused` and `refused.reason: "Empty working directory."`. Otherwise note `detected_stacks` from `package.json` / `pyproject.toml` / `requirements.txt` for reporting (the workflow does not branch on this).

2. **Render the new workflow.** Copy `assets/security-scan.yml` verbatim to `/tmp/new-workflow.yml`.

3. **Read existing target if present.** Use Read on `.github/workflows/security-scan.yml`. If the file does not exist, treat it as DIFF and proceed to step 5 with `status: created`.

4. **Idempotency check.** If the file existed in step 3:

   ```bash
   bash .claude/skills/security-scan/scripts/compare_yaml.sh .github/workflows/security-scan.yml /tmp/new-workflow.yml
   ```

   If the output is `SAME`:
   - Do not write, do not commit, do not push.
   - Get the previous commit URL: `git log -1 --format="%H" -- .github/workflows/security-scan.yml` and the repo URL via `git config --get remote.origin.url`.
   - Get the existing PR URL via `bash .claude/skills/security-scan/scripts/ensure_pr.sh`.
   - Emit the JSON output with `status: "no_change"` and stop.

   If the output is `DIFF`, set `status: "updated"` and continue.

5. **Switch to the demo branch.**

   ```bash
   bash .claude/skills/security-scan/scripts/switch_to_demo_branch.sh
   ```

6. **Write the workflow file.** Ensure `.github/workflows/` exists, then Write the contents of `/tmp/new-workflow.yml` to `.github/workflows/security-scan.yml`.

7. **Commit and push.**

   ```bash
   git add .github/workflows/security-scan.yml
   git commit -m "ci: add security-scan workflow via security-scan skill"
   git push -u origin claude/ci-demo
   ```

8. **Ensure the PR exists.**

   ```bash
   bash .claude/skills/security-scan/scripts/ensure_pr.sh
   ```

   Capture the printed URL as `pr_url` for the final JSON.

9. **Read the resulting GitHub Actions runs.**

   ```bash
   bash .claude/skills/security-scan/scripts/list_workflow_runs.sh security-scan.yml
   ```

10. **Emit the output JSON.** See "Output format" below.

## Output format

After completing the steps (or on early exit from step 1 or step 4), emit exactly one JSON code block as the final content of your response. Do not add prose after it.

```json
{
  "skill": "security-scan",
  "status": "created" | "updated" | "no_change" | "refused",
  "branch": "claude/ci-demo",
  "workflow_path": ".github/workflows/security-scan.yml",
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

Status semantics match the other CI/CD skills (`created`, `updated`, `no_change`, `refused`). On `no_change`, `commit_url` is the previous commit looked up via `git log`.
