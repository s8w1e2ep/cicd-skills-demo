# plan.md — Implementation plan

## 1. Architecture

```
       ┌────────────────────────────────────────────┐
       │  Browser / curl                            │
       └────────────────┬───────────────────────────┘
                        │ POST /run {prompt}
                        ▼
       ┌────────────────────────────────────────────┐
       │  FastAPI (server/main.py)                  │
       │  ─ clone demo repo → /tmp/work-<uuid>      │
       │  ─ launch claude-agent-sdk query()         │
       │      • cwd = scratch dir                   │
       │      • setting_sources=["project"] loads   │
       │        <cwd>/.claude/skills/               │
       │      • prompt forwarded                    │
       │  ─ wait for completion (90s timeout)       │
       │  ─ parse final JSON code block from output │
       └────────────────┬───────────────────────────┘
                        │ Claude routes prompt
                        ▼
       ┌────────────────────────────────────────────┐
       │  Claude (in CWD) follows SKILL.md:         │
       │  ─ Read package.json / pyproject.toml      │
       │  ─ Read assets/<stack>.yml template        │
       │  ─ Compute target path                     │
       │  ─ If existing: python3 -c yaml-compare    │
       │       → SAME: emit no_change JSON, stop    │
       │       → DIFF: continue                     │
       │  ─ Write workflow YAML                     │
       │  ─ Bash: git checkout -B claude/ci-demo,   │
       │           add, commit, push                │
       │  ─ Bash: gh pr create or skip if exists    │
       │  ─ Bash: gh run list --branch ...          │
       │  ─ Emit final JSON code block              │
       └────────────────┬───────────────────────────┘
                        │ commit + push to claude/ci-demo
                        ▼
       ┌────────────────────────────────────────────┐
       │  GitHub Actions runner                     │
       │  ─ executes the YAML                       │
       │  ─ Service returns links; grader clicks    │
       └────────────────────────────────────────────┘
```

Key choice: **Skills are pure markdown + assets, no custom helpers.** Claude follows SKILL.md using its native Read / Write / Bash. The server is a thin orchestrator.

## 2. Components

### 2.1 Skills (`.claude/skills/<name>/`)

Per official skill-creator + claude-agent-sdk:

```
.claude/skills/<name>/
├── SKILL.md             # < 500 lines, frontmatter + body
├── assets/              # workflow YAML templates per language stack
│   ├── <name>.node.yml
│   └── <name>.python.yml
└── evals/
    └── evals.json
```

Path is fixed by SDK discovery: `setting_sources=["project"]` loads from `<cwd>/.claude/skills/`. Demo repo is this project repo, so the scratch clone naturally has `.claude/skills/`.

`SKILL.md` body sections:

1. **When to use** — specific trigger contexts (already in description, restated for the body's audience: Claude after invocation)
2. **Steps** — imperative numbered list: detect, read template, check existing, compare, write, commit, push, ensure PR, list runs
3. **Idempotency check** — exact `python3 -c …` command to run; what to do on SAME vs DIFF
4. **Output format** — the JSON schema, with example values

Descriptions follow skill-creator's "pushy" guidance — include trigger phrases like "lint", "tests", "CI", "workflow", "GitHub Actions" explicitly, and a sentence that says "use this even if the user doesn't say <X>".

### 2.2 Server (`server/main.py`)

- FastAPI with the four endpoints from spec §4.8.
- Synchronous handler:
  1. Reject if `repo_url` ≠ `DEMO_REPO_URL` env (allowlist enforced server-side).
  2. `git clone --depth=20 $DEMO_REPO_URL /tmp/work-<uuid>` (depth > 1 so we can see existing branches).
  3. `cd /tmp/work-<uuid>` and `git fetch origin claude/ci-demo` (best-effort; may not exist).
  4. Invoke `claude_agent_sdk.query()` with `cwd=<scratch>`, `setting_sources=["project"]` (loads `.claude/skills/` from cwd), `allowed_tools=["Skill","Read","Write","Edit","Bash","Grep","Glob"]`, prompt forwarded.
  5. 90s hard timeout.
  6. Parse the last JSON code block from stdout.
  7. Validate against the output schema.
  8. Clean up scratch dir.
- The agent's tool set: `Read`, `Write`, `Bash`. We rely on the demo repo's CWD being a scratch dir for safety; `Bash` is needed for `git`/`gh`/`python3`.

### 2.3 Demo UI (`server/static/index.html`)

Single file, vanilla JS. 6 preset chips. Result pane parses returned JSON, renders clickable links. "Run again" button.

### 2.4 Eval harness (`eval/run_eval.py`)

- Reads `eval/prompts.jsonl`.
- For each entry: `POST /run` → record returned `skill` (or `refused`) → compare to `expected_skill` → per-category precision.
- Writes `eval/results/<timestamp>.md`.

Per-skill `evals.json` files exist but are aspirational in v1 — graders can run them manually; we don't build a runner for them in the time budget. Documented as a follow-up.

### 2.5 Deploy

- `Dockerfile`: `python:3.12-slim` + `gh` CLI + `git` + `pyyaml`. Install Python deps from `requirements.txt`.
- Zeabur env vars: `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, `DEMO_REPO_URL`.

## 3. Trade-offs

| Decision | Alternative | Why |
|---|---|---|
| Pure-markdown Skills (no custom Python helpers) | Wrap each Skill in a deterministic Python program | Idiomatic per skill-creator; lets the AI-collaboration evidence show; idempotency provided by an explicit semantic-compare step inside SKILL.md, not by hiding logic from Claude |
| Inline `python3 -c "…yaml.safe_load…"` for compare | Ship `scripts/compare_yaml.py` per skill | One-liner is short enough; avoids per-skill duplication; SKILL.md is more readable when the check is visible |
| Single shared `claude/ci-demo` branch + persistent PR | Per-skill branch / fresh PR | Demo cleanliness; one PR shows all four contributions; idempotency trivial |
| Templates in `assets/` per language stack | LLM generates YAML on the fly | Idempotency requires byte-deterministic output. Templates eliminate LLM drift |
| Server enforces repo allowlist (one demo repo only) | Trust the agent | Hard wall — even a jailbroken agent cannot touch other repos |
| Agent picks the Skill (`/run`) + manual override (`/run/skill/{name}`) | Force user to pick | Routing is the trigger-precision evaluation; manual path serves eval harness + debug |
| Single fine-grained PAT | GitHub App OAuth | OAuth + `workflows` scope is 2+ hours; documented as production-migration item |
| Synchronous API, return run URL (don't poll) | Async + SSE | The run lives 1–5 min on GitHub; linking out is honest and saves 30+ min |
| 15-prompt routing eval | 50–100 prompts | Optimising for category coverage, not statistical power |
| Per-skill `evals/evals.json` exists but no runner in v1 | Build a per-skill runner too | Out of time budget; stub the data, document as follow-up |

## 4. Risks

- **R1: `workflows` scope rejected** by org policy. Pre-verify on demo repo before sharing URL.
- **R2: First run with no `claude/ci-demo` branch.** SKILL.md instructs Claude to `git checkout -B` (creates if missing).
- **R3: GitHub Actions doesn't trigger.** Templates default `on: [push, pull_request]`.
- **R4: Idempotency false positives** if templates contain non-deterministic content. Templates are static files with `{stack-specific}` placeholders only — no timestamps, no nonces.
- **R5: Claude skips the idempotency check.** Mitigation: SKILL.md frames the check as the very first step after detection, not as an afterthought; output schema makes `no_change` an explicit, valued status; eval includes idempotency cases that catch regressions.
- **R6: Final JSON parsing fails** because Claude added prose after the block. Mitigation: SKILL.md instruction is "Do not add prose after the JSON block"; server parser takes the LAST JSON block in stdout, not the first.
- **R7: 1–2h overrun.** Phase priority cuts in `task.md`; README's failure-modes section is non-negotiable.

## 5. Sequence

1. Skeleton + `lint-and-test` Skill end-to-end (SKILL.md, asset, server with `/run/skill/lint-and-test`, real commit + GitHub Actions run).
2. Other three Skills.
3. `/run` agent routing + UI.
4. Eval set + harness + first run.
5. Idempotency + safety smoke.
6. README + `prompts/` + Zeabur deploy.

Detailed steps in `task.md`.
