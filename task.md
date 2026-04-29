# task.md — Ordered task list

Time budget: **90–120 minutes total**. Order matters more than the numbers.

Each phase ends in a **commit** with an intent-revealing message. The grader will read `git log`.

---

## Phase 0 — Repo init  (≈ 5 min)

- [x] `git init` inside `cicd-skills-demo/`
- [x] `.gitignore`: Python, `.env`, `/tmp`, scratch dirs, `eval/results/*.md` (keep one sample)
- [x] First commit: "scaffold spec/plan/task docs and CLAUDE.md"
- [ ] Push this repo to GitHub as a public repo — **this same repo is the demo target** (Skills operate on it). User does this when ready.
- [ ] Generate fine-grained PAT scoped to this repo: `Contents: write` + `Workflows: write` + `Pull requests: write` + `Actions: read`. Stored as Zeabur secret env var `GITHUB_TOKEN`; not needed locally.
- [ ] `ANTHROPIC_API_KEY` will also be a Zeabur secret env var; not needed locally.

## Phase 1 — One Skill end-to-end  (≈ 30 min)

Goal: prove the loop works for `lint-and-test` before scaling.

- [x] `.claude/skills/lint-and-test/SKILL.md` — frontmatter (pushy description) + body sections (when to use, steps, idempotency check, output format)
- [x] `.claude/skills/lint-and-test/assets/lint-and-test.node.yml` — static template
- [x] `.claude/skills/lint-and-test/assets/lint-and-test.python.yml` — static template
- [x] `.claude/skills/lint-and-test/evals/evals.json` — 2 entries (happy + idempotency)
- [x] `server/main.py` — both `/run` (agent routing) and `/run/skill/{name}` (forced) shipped together since the SDK exposes both at once
- [x] `Dockerfile` written; build verified during Zeabur deploy
- [ ] Smoke test against demo repo (Zeabur 502 — pending deploy fix)
- [ ] Re-run with same input → confirm `status: no_change` (pending deploy fix)
- [x] **Commit**: `Phase 1: FastAPI server + Dockerfile + Zeabur config`

## Phase 2 — Remaining three Skills  (≈ 25 min)

For each Skill: SKILL.md + assets + evals/evals.json (≥ 2 entries).

- [x] `.claude/skills/dependency-audit/` (npm audit + pip-audit)
- [x] `.claude/skills/security-scan/` (gitleaks + semgrep, SARIF to Security tab)
- [x] `.claude/skills/build-and-release/` (tag-on-push, npm pack / python -m build, GitHub Release)
- [x] `/run/skill/{name}` already dispatches by name — `KNOWN_SKILLS` covers all four
- [ ] Smoke test each Skill against demo repo (pending deploy fix)
- [x] **Commit**: `Phase 2: dependency-audit, security-scan, build-and-release Skills`

## Phase 3 — Agent routing + UI  (≈ 15 min)

Folded into Phase 1 — the SDK exposes both `/run` (agent routing) and `/run/skill/{name}` (forced) at once, so they shipped in the same commit.

- [x] `POST /run` — loads all four Skills via Claude Agent SDK; Claude picks; parse final JSON
- [x] Repo allowlist (`DEMO_REPO_URL` env) enforced at both endpoints
- [x] `GET /healthz` returns 200
- [x] `GET /` serves `static/index.html` with 6 preset chips + result pane + "Run again" button
- [x] Smoke test against live URL — passing

## Phase 4 — Eval set + harness  (≈ 15 min)

- [x] `eval/prompts.jsonl` — 16 entries: 9 trigger / 4 ambiguous / 3 safety, realistic & messy per skill-creator guidance
- [x] `eval/run_eval.py` — pure-stdlib harness; per-category precision; markdown report; non-zero exit on trigger precision < 0.85
- [x] Ran against live URL; report at `eval/results/eval-20260430-022545.md` (trigger 100% / ambiguous 50% / safety 100% / overall 88%)
- [x] Description revision cycle skipped — trigger 100% means no win to claim from a v2; documented in `prompts/06-eval-misses-analysis.md`
- [x] **Commit**: `Phase 4 + 6: eval harness + README`

## Phase 5 — Idempotency + safety smoke  (≈ 5 min)

The harness in Phase 4 already hits 3 safety prompts; this phase is the
explicit two-run idempotency check + the non-allowlisted-repo rejection.

- [x] `lint-and-test` preset twice → second response `status: no_change`, no new commit on `claude/ci-demo` (verified with PR #1's commit log)
- [x] Destructive prompt → `status: refused` via `NO_SKILL_FALLBACK_INSTRUCTION` wrapper (3/3 safety prompts in eval)
- [x] Request with non-allowlisted `repo_url` → server rejects with HTTP 400 (covered by `tests/test_main.py::test_run_rejects_non_allowlisted_repo_url`)

## Phase 6 — README + prompts/  (≈ 15 min)

- [x] `README.md` — architecture, scoring-axis verification map, auth caveats, honest failure modes, AI-collaboration links, live URL
- [x] `prompts/01-framing-corrections.md` — user pushbacks that re-architected the project
- [x] `prompts/02-skill-creator-alignment.md` — skill-creator WebFetch + structural changes
- [x] `prompts/03-sdk-discovery.md` — claude-agent-sdk research with quoted citations
- [x] `prompts/04-lint-and-test-description-v1.md` — annotated description rationale
- [x] `prompts/05-eval-prompt-design.md` — the 16 prompts.jsonl entries' construction logic
- [x] `prompts/06-eval-misses-analysis.md` — post-eval analysis of the two ambiguous misses + wrapper trade-off
- [x] **Commit**: `Phase 4 + 6: eval harness + README`

## Phase 7 — Zeabur deploy  (≈ 10 min)

- [x] `zeabur.json` declaring health check + required env vars
- [x] Push to public GitHub repo (`s8w1e2ep/cicd-skills-demo`)
- [x] Zeabur connected; env vars set; container built and deployed
- [x] Live URL allocated: https://cicd-demo.zeabur.app/
- [x] Live URL added to README
- [x] `/healthz` returning 200
- [x] All four Skills run end-to-end against demo repo — see PR #1
- [x] Switched auth from API key to OAuth token (Pro/Max subscription) when API credit was unavailable

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
