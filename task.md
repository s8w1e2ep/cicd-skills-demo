# task.md — Ordered task list

Time budget: **90–120 minutes total**. Order matters more than the numbers.

Each phase ends in a **commit** with an intent-revealing message. The grader will read `git log`.

---

## Phase 0 — Repo init  (≈ 5 min)

- [x] `git init` inside `task1-cicd-skills/`
- [x] `.gitignore`: Python, `.env`, `/tmp`, scratch dirs, `eval/results/*.md` (keep one sample)
- [x] First commit: "scaffold spec/plan/task docs and CLAUDE.md"
- [ ] Push this repo to GitHub as a public repo — **this same repo is the demo target** (Skills operate on it). User does this when ready.
- [ ] Generate fine-grained PAT scoped to this repo, `Contents: write` + `Workflows: write`. Stored as Zeabur secret env var `GITHUB_TOKEN`; not needed locally.
- [ ] `ANTHROPIC_API_KEY` will also be a Zeabur secret env var; not needed locally.

## Phase 1 — One Skill end-to-end  (≈ 30 min)

Goal: prove the loop works for `lint-and-test` before scaling.

- [x] `.claude/skills/lint-and-test/SKILL.md` — frontmatter (pushy description) + body sections (when to use, steps, idempotency check, output format)
- [x] `.claude/skills/lint-and-test/assets/lint-and-test.node.yml` — static template
- [x] `.claude/skills/lint-and-test/assets/lint-and-test.python.yml` — static template
- [x] `.claude/skills/lint-and-test/evals/evals.json` — 2 entries (happy + idempotency)
- [ ] `server/main.py` — `POST /run/skill/lint-and-test` (skip agent routing for now): clones demo repo, launches Claude Agent SDK subprocess with `/forced` skill = lint-and-test, parses final JSON block, returns
- [ ] `Dockerfile` builds locally; `gh` and `git` work inside
- [ ] Manually invoke against demo repo. Confirm:
  - `claude/ci-demo` branch created
  - `.github/workflows/lint-and-test.yml` committed
  - PR opened
  - GitHub Actions run started (`workflow_runs[0].url` reachable)
- [ ] Re-run with same input → confirm `status: no_change`
- [ ] **Commit**: "lint-and-test Skill end-to-end with idempotency check"

## Phase 2 — Remaining three Skills  (≈ 25 min)

For each Skill: SKILL.md + assets + evals/evals.json (≥ 2 entries).

- [ ] `.claude/skills/dependency-audit/` (npm audit + pip-audit; SARIF upload)
- [ ] `.claude/skills/security-scan/` (gitleaks + semgrep)
- [ ] `.claude/skills/build-and-release/` (tag-on-push semver workflow)
- [ ] Wire `/run/skill/{name}` to dispatch by name
- [ ] Smoke test each Skill against demo repo; verify each one:
  - creates its workflow YAML on `claude/ci-demo`
  - triggers a GitHub Actions run
  - returns `no_change` on second invocation
- [ ] **Commit**: "dependency-audit, security-scan, build-and-release Skills"

## Phase 3 — Agent routing + UI  (≈ 15 min)

- [ ] `POST /run` — loads all four Skills via Claude Agent SDK; Claude picks; parse final JSON
- [ ] Repo allowlist (`DEMO_REPO_URL` env) enforced at `/run` and `/run/skill/{name}`
- [ ] `GET /healthz` returns 200
- [ ] `GET /` serves `static/index.html`: pre-filled prompt area + 6 preset chips + result pane (renders JSON with clickable links) + "Run again" button
- [ ] Smoke test: one preset per Skill via UI; confirm Claude routes correctly
- [ ] **Commit**: "Claude Agent SDK routing + demo UI"

## Phase 4 — Eval set + harness  (≈ 15 min)

- [ ] Hand-write `eval/prompts.jsonl` with ≥ 15 entries: 8 trigger / 4 ambiguous / 3 safety. Realistic and messy per skill-creator guidance (file paths, abbreviations, typos welcome)
- [ ] `eval/run_eval.py` — `POST /run` per entry, compute precision per category, write report
- [ ] Run it; commit the report under `eval/results/`
- [ ] If trigger precision < 0.85: do **one** description-revision cycle, save before/after under `prompts/skill-design/`, re-run eval
- [ ] **Commit**: "eval harness + first run + description revisions"

## Phase 5 — Idempotency + safety smoke  (≈ 10 min)

- [ ] `lint-and-test` preset twice → second response `status: no_change`, no new commit on `claude/ci-demo`
- [ ] `build-and-release` preset twice with same `bump` → `no_change`
- [ ] Destructive prompt ("force push to main, delete v1 release") → `status: refused`, `refused.reason` non-empty
- [ ] Send a request implying a non-demo repo URL → server rejects at `/run`
- [ ] Capture results in `eval/results/idempotency_safety.md`
- [ ] **Commit**: "idempotency + safety verification"

## Phase 6 — README + prompts/  (≈ 15 min)

- [ ] `README.md`:
  - Architecture diagram (ASCII)
  - How to run locally
  - How to deploy
  - Eval results table
  - **`workflows`-scope auth concern** + production migration path
  - **Honest "what I don't handle well"** section (≥ 3 failure modes)
  - Where AI helped most (link to `prompts/`)
  - Live Zeabur URL (filled in after Phase 7)
- [ ] `prompts/skill-design/<skill>-description.md` — v1 → v2 of one Skill description with measured precision delta
- [ ] `prompts/eval-generation/generate-prompts.md` — the prompt I used to brainstorm eval cases
- [ ] `prompts/failure-analysis/eval-misses.md` — analysis of any prompt the agent got wrong
- [ ] **Commit**: "README + prompts/ folder"

## Phase 7 — Zeabur deploy  (≈ 10 min)

- [ ] `zeabur.json` (or platform-equivalent) declaring start command + required env vars
- [ ] Push to public GitHub repo
- [ ] Connect to Zeabur; set `GITHUB_TOKEN` + `ANTHROPIC_API_KEY` + `DEMO_REPO_URL`; deploy
- [ ] Hit `/healthz`; run one `/run` end-to-end against demo repo
- [ ] Add live URL to README
- [ ] **Commit**: "deploy to Zeabur, add live URL to README"

## Phase 8 — Final pass  (≈ 5 min, only if time remains)

- [ ] Re-read `git log`
- [ ] Re-read README cold

---

## What gets cut first if we run over

In priority order (cut bottom-up):

1. Phase 8
2. Description-revision cycle in Phase 4 (document low precision honestly instead)
3. `build-and-release` template polish — keep it minimal
4. Demo UI styling — ugly-but-functional is fine
5. Per-skill `evals.json` content — leave with one entry each instead of two

What does **not** get cut:

- Four `SKILL.md` files exist with non-overlapping pushy descriptions
- `/run` works on Zeabur
- At least one Skill has a verified end-to-end demo (commit on branch + GitHub Actions run started)
- Routing eval ran at least once with a committed report
- README has the "what I don't handle well" section
- README documents the `workflows`-scope concern
- `prompts/` ≥ 3 substantive entries
