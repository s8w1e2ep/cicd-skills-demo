# spec.md — Task 1: GitHub CI/CD as Claude Skills

## 1. Background & framing

The interview prompt asks for "common GitHub CI/CD workflows packaged into a few reusable Claude Skills." Clarified with the project owner:

- A Skill's job is to **author / update a `.github/workflows/*.yml` file in the current repo**, plus commit + push + ensure PR.
- Actual CI/CD execution is performed by **GitHub Actions runners**, not our Zeabur service.
- "Skills running against a real repo" = Skills maintaining workflow YAML in a real repo, with GitHub Actions runs serving as proof.
- The Skills must be **idiomatic Claude Skills** — markdown instructions Claude follows using its native Read / Write / Bash tools. Not Python programs wearing a SKILL.md hat.

The four scoring axes, re-interpreted under this framing:

| Axis | What it means here |
|---|---|
| Skill boundaries | One Skill = one workflow YAML kind. No overlap, no Skill writes more than one file. |
| Auth & safety | PAT requires the sensitive `workflows` scope; we scope it to one demo repo and document the production migration path. The service hard-rejects any other repo. |
| Idempotency | Re-running with identical input must NOT create a duplicate commit / PR / workflow. SKILL.md instructs Claude to read existing YAML, semantic-diff it, and skip if equal. |
| Trigger precision | Claude picks the right Skill from a natural-language prompt. The `description:` frontmatter is the routing signal. |

We follow the official skill-creator guidelines (anthropics/skills repo): three-level progressive disclosure (metadata → SKILL.md body → bundled resources), pushy descriptions to combat undertriggering, explicit output format templates, imperative instructions explaining the "why".

## 2. Goals

- G1. Four idiomatic Claude Skills with crisp, non-overlapping responsibilities (one workflow YAML each).
- G2. A demo service on Zeabur where a grader can issue a natural-language request and see (a) Claude pick a Skill, (b) a real commit on `claude/ci-demo` of the demo repo, (c) a real GitHub Actions run start.
- G3. Eval harness measuring trigger precision (target ≥ 0.85) + per-skill idempotency.
- G4. Honest failure-mode documentation in the README.
- G5. `prompts/` folder showing how AI shaped design decisions, not just produced code.

## 3. Non-goals (cut for the 1–2h time budget)

- Non-YAML configuration. v1 produces workflow YAML only — no `dependabot.yml`, `.semgrep.yml`, CodeQL config files.
- Per-Skill branches. All four Skills share `claude/ci-demo`.
- GitHub App OAuth — single fine-grained PAT, scoped to one demo repo.
- Real-time GitHub Actions run-status streaming — return run URL, grader clicks through.
- Multi-tenancy, queueing, request authn.

## 4. Functional requirements

### 4.1 Skill catalog

Each Skill produces exactly one file under `.github/workflows/` of the current repo:

| Skill | Output file | Generated workflow |
|---|---|---|
| `lint-and-test` | `lint-and-test.yml` | Detect stack(s); run language-canonical lint + test (eslint+jest, ruff+pytest). |
| `dependency-audit` | `dependency-audit.yml` | Run `npm audit` / `pip-audit`; fail on high+ severity. |
| `security-scan` | `security-scan.yml` | Run gitleaks + semgrep (default ruleset); upload SARIF. |
| `build-and-release` | `release.yml` | Tag-on-push semver workflow; build artifact; create GitHub Release. |

### 4.2 Skill folder structure (per official skill-creator)

```
skills/<name>/
├── SKILL.md             # required: frontmatter + body (< 500 lines)
├── assets/              # workflow YAML templates, one per language stack
│   └── *.yml
└── evals/
    └── evals.json       # per-skill evals (skill execution correctness)
```

`scripts/` and `references/` are not used in v1 — SKILL.md stays compact, and the YAML semantic-compare we need is a one-line `python3 -c …` invocation that fits inline in the body.

### 4.3 Inputs (implicit)

Skills take **no explicit parameters**. The Skill operates on the current working directory — Claude reads `package.json`, `pyproject.toml`, etc. to detect stacks. The user's natural-language prompt is the only "input" beyond the CWD; the Skill body interprets it.

The Zeabur server is responsible for cloning the demo repo into a scratch dir and launching Claude Agent SDK with that as CWD.

### 4.4 Output format

Each SKILL.md ends with an explicit output template. After execution Claude must emit a single JSON code block as the final content of its response, matching:

```json
{
  "skill": "lint-and-test",
  "status": "created" | "updated" | "no_change" | "refused",
  "branch": "claude/ci-demo",
  "workflow_path": ".github/workflows/lint-and-test.yml",
  "commit_url": "https://github.com/<owner>/<repo>/commit/<sha>" | null,
  "pr_url": "https://github.com/<owner>/<repo>/pull/<n>" | null,
  "workflow_runs": [
    {"url": "...", "status": "queued|in_progress|completed", "conclusion": null|"success"|"failure"}
  ],
  "detected_stacks": ["node", "python"],
  "notes": "<one short sentence — caveats, assumptions, or empty>",
  "refused": null | {"reason": "<why this skill should not run on this repo>"}
}
```

Status semantics:
- `created` — workflow file did not exist; written for the first time.
- `updated` — file existed but new content differs semantically; commit pushed.
- `no_change` — file exists and is semantically equal to rendered version; no commit. `commit_url` reflects previous commit.
- `refused` — preconditions not met. No commit. `refused.reason` populated.

The server parses Claude's final JSON block; downstream UI consumes the structured object.

### 4.5 Branch & PR strategy

- All Skills push to `claude/ci-demo`, branched from the demo repo's default branch.
- A single PR `claude/ci-demo → main` is maintained — created on first run, kept open thereafter.
- Branch never force-pushed. New commits append.
- Re-running with identical input → `no_change` → no new commit, no PR update.

### 4.6 Idempotency mechanism (instructed in SKILL.md)

Each SKILL.md includes a step like:

> Before writing, if the target file already exists, run this exact command to check semantic equality:
> ```
> python3 -c "import sys, yaml; a=yaml.safe_load(open(sys.argv[1])); b=yaml.safe_load(open(sys.argv[2])); print('SAME' if a==b else 'DIFF')" <existing> <new>
> ```
> If output is `SAME`, skip the write/commit/push entirely and return status `no_change` with the previous commit URL (find it via `git log -1 --format=%H -- <path>`).

### 4.7 Auth & safety

- `GITHUB_TOKEN` env: fine-grained PAT scoped to **one demo repo only**, with `Contents: write` and `Workflows: write`.
- The `workflows` scope is sensitive — workflows can read repo secrets. README must call this out and propose GitHub App + per-installation tokens as the production migration path.
- Server hard-rejects any request whose target repo doesn't match the env-allowlisted demo repo. This is the primary safety wall.
- Destructive operations (delete branch, force push, remove existing workflow, delete release) are not Skills. Claude must produce `status: refused` with a reason.

### 4.8 Demo API

- `POST /run` — body `{prompt: str}`. Server clones demo repo to scratch, invokes Claude Agent SDK with skills/ loaded, prompt passed; parses final JSON block; returns it plus duration.
- `POST /run/skill/{name}` — bypass routing; force a specific Skill (for eval harness + debugging).
- `GET /healthz` — liveness.
- `GET /` — single-page demo UI.

### 4.9 Demo UI requirements

- 6 preset chips: one per Skill + one ambiguous + one destructive.
- Result pane shows `skill` prominently, plus clickable `commit_url`, `pr_url`, `workflow_runs[].url`.
- "Run again" button — re-runs same input — purpose is to make `status: no_change` visible.

## 5. Eval requirements

Two layers:

### 5.1 Global routing eval (project root)

`eval/prompts.jsonl` ≥ 15 entries:

```json
{"prompt": "...", "expected_skill": "lint-and-test|...|REFUSE", "category": "trigger|ambiguous|safety"}
```

- **trigger** (≥ 8): unambiguous single-Skill cases. Realistic, messy prompts (per skill-creator: "include personal context, file paths, abbreviations, typos").
- **ambiguous** (≥ 4): plausibly two Skills.
- **safety** (≥ 3): destructive prompts that must yield `status: refused`.

`eval/run_eval.py` posts each prompt to `/run`, compares `skill` field to `expected_skill`, computes per-category precision, writes `eval/results/<timestamp>.md`.

### 5.2 Per-skill evals

Each `skills/<name>/evals/evals.json` follows the official schema:

```json
{
  "skill_name": "lint-and-test",
  "evals": [
    {"id": 1, "prompt": "set up CI for tests", "expected_output": "creates lint-and-test.yml on claude/ci-demo, status=created", "files": []}
  ]
}
```

≥ 2 entries per skill, including one idempotency case (same input twice → second run `no_change`).

## 6. Acceptance criteria

- [ ] Four `SKILL.md` files with distinct, "pushy" descriptions following skill-creator guidelines (each describes WHAT and WHEN to use).
- [ ] Each Skill has `assets/*.yml` templates and `evals/evals.json` (≥ 2 entries).
- [ ] For each Skill, `/run` produces a real commit on `claude/ci-demo`, opens/updates the PR, triggers a GitHub Actions run.
- [ ] Same call repeated → `status: no_change`, no new commits.
- [ ] At least one destructive prompt verifiably refused (`status: refused`, `refused.reason` non-empty).
- [ ] `eval/run_eval.py` runs to completion; trigger-category precision ≥ 0.85 reported.
- [ ] README documents architecture, run instructions, the `workflows`-scope auth concern, eval results, ≥ 3 honest failure modes.
- [ ] `prompts/` ≥ 3 substantive entries (one shows description iteration with measured precision delta).
- [ ] Service reachable on Zeabur; `/healthz` 200.
- [ ] ≥ 8 commits with intent-revealing messages.

## 7. Out of scope (explicit)

- Stacks beyond Node/Python.
- Detecting and respecting pre-existing user workflows (we operate only on files we own under `.github/workflows/`).
- Streaming GitHub Actions run status — return the URL only.
- Authn on the demo API (anyone with the URL can run; documented; the repo allowlist is the wall).
