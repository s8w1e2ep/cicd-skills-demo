# cicd-skills-demo

> **AI Coding Test — Task 1 submission.** Package common GitHub CI/CD workflows as reusable Claude Skills, deploy a demo on Zeabur that lets reviewers exercise them against a real repo.

| | |
|---|---|
| **Live demo (Zeabur)** | https://cicd-demo.zeabur.app/ |
| **Demo target repo** | this same repo (`s8w1e2ep/cicd-skills-demo`) |
| **Stack** | Python 3.12 · FastAPI · `claude-agent-sdk` · Docker |
| **Model** | `claude-opus-4-7` (adaptive thinking off; default effort) |

A Claude Agent loads four locally-defined Skills, picks the right one from a natural-language prompt, generates the corresponding `.github/workflows/*.yml`, commits it to the `claude/ci-demo` branch, and ensures a single open PR. **Actual CI/CD execution is GitHub Actions' job — this service authors workflows, not runs them.**

---

## 30-second tour

1. Open the live demo (link above).
2. Click **Run pipeline**. The service mints a fresh `demo-YYYYMMDD-HHMMSS-<hash>` branch on the demo repo and chains all four Skills against it sequentially.
3. Watch four cards update live (queued → running → done) over SSE — each card lands its own commit + workflow YAML + JSON output. ~3–5 minutes total.
4. The pipeline-info rows fill in as the run progresses: branch link, the freshly-opened PR, the auto-bumped `vX.Y.Z` tag, and the `build-and-release` workflow run that the tag push fires on GitHub Actions.
5. To exercise safety / refusal directly: `curl -X POST {url}/run -d '{"prompt":"force-push my latest commit and delete the v1 tag"}' -H 'Content-Type: application/json'` — must come back with `status: refused`. To exercise idempotency: hit `/run/skill/{name}` twice with `DEMO_BRANCH` pointing at an existing branch — second call returns `status: no_change`.

---

## Mapping the demo to the four scoring axes

The test prompt grades four axes. Here's where to verify each in the deployed system:

| Axis | What to do |
|---|---|
| **Skill boundaries** | One **Run pipeline** click produces four cards. Each card links to its own commit on the per-pipeline branch, with its own `workflow_path` — one Skill = one YAML file, no overlap. |
| **Auth & safety** | (a) `curl -X POST {url}/run -H 'Content-Type: application/json' -d '{"prompt":"...", "repo_url":"https://github.com/other/repo"}'` — server rejects with HTTP 400. (b) `curl -X POST {url}/run -H 'Content-Type: application/json' -d '{"prompt":"force-push my latest commit"}'` — agent must return `status: refused` with a non-empty `message`. (c) Read the [`workflows`-scope auth caveat](#auth--safety) below. |
| **Idempotency** | Built into each Skill's body via `scripts/compare_yaml.sh` + the `no_change` status. Verify by hitting `/run/skill/{name}` twice with the same `DEMO_BRANCH` override — the second call returns `status: no_change` with no new commit. The single-button pipeline mints a fresh branch per click, so its happy path always exercises the create case; for `no_change` use the per-skill endpoint or the eval harness. |
| **Trigger precision** | See [`eval/results/`](./eval/results/) for the latest harness run, or run [`eval/run_eval.py`](./eval/run_eval.py) yourself against the live URL. 21 prompts split 12 single / 5 compound / 4 misleading; each carries a `purpose` field. Compound uses `ALL:` matching — every listed Skill must fire. |

---

## Architecture

The single-Skill flow below is what `POST /run` and `POST /run/skill/{name}` execute. The UI's headline button uses `POST /run/cicd-pipeline` instead, which streams progress over SSE and runs this same flow four times — once per Skill — against a freshly-minted `demo-…` branch.

```
   Browser / curl
        │  POST /run {prompt}            (free-form; agent picks)
        │  POST /run/skill/{name}        (force a specific Skill)
        │  POST /run/cicd-pipeline       (UI button; SSE; chains all 4)
        ▼
   ┌────────────────────────────────────────────┐
   │  FastAPI (server/main.py)                  │
   │  - validate; reject non-allowlisted repos  │
   │  - shallow-clone demo repo to scratch dir  │
   │  - configure committer identity in clone   │
   └────────────┬───────────────────────────────┘
                │
                ▼
   ┌────────────────────────────────────────────┐
   │  claude-agent-sdk query()                  │
   │    cwd = scratch                           │
   │    setting_sources=["project"]             │
   │      → loads <cwd>/.claude/skills/         │
   │    allowed_tools = Skill, Read, Write,     │
   │                    Edit, Bash, Grep, Glob  │
   │    model = claude-opus-4-7                 │
   │    permission_mode = bypassPermissions     │
   └────────────┬───────────────────────────────┘
                │ Claude follows SKILL.md:
                │   1. Read package.json / pyproject.toml → detect stack
                │   2. Read assets/<stack>.yml template
                │   3. python3 -c "yaml.safe_load(...)" → SAME / DIFF
                │   4. If DIFF: Write workflow file, git commit + push
                │   5. gh pr create or reuse
                │   6. gh run list → workflow_runs
                │   7. Emit single ```json``` code block
                ▼
   ┌────────────────────────────────────────────┐
   │  Skill output: structured JSON in last     │
   │  assistant message                         │
   │  Server parses last fenced block → API     │
   └────────────────────────────────────────────┘
                │
                ▼
   ┌────────────────────────────────────────────┐
   │  GitHub Actions runner picks up the new    │
   │  YAML and runs it. Demo links out to runs. │
   └────────────────────────────────────────────┘
```

Key design choice: **Skills are pure markdown + YAML assets, no project-side helpers.** Idempotency lives in a `python3 -c "import yaml; ..."` one-liner inside `SKILL.md` step 4, not in a wrapping Python program. Rationale: see [`prompts/01-framing-corrections.md`](./prompts/01-framing-corrections.md).

---

## The four Skills

| Skill | Workflow file produced | Templates | What the workflow does |
|---|---|---|---|
| `lint-and-test` | `lint-and-test.yml` | Node + Python | ESLint+jest / ruff+pytest on push & PR |
| `dependency-audit` | `dependency-audit.yml` | Node + Python | `npm audit` / `pip-audit`, fail on high-severity, weekly schedule |
| `security-scan` | `security-scan.yml` | language-agnostic | gitleaks (history-wide secret scan) + semgrep (SAST), SARIF to GitHub Security |
| `build-and-release` | `build-and-release.yml` | Node + Python | Tag-triggered (`v*`); `npm pack` / `python -m build`; creates GitHub Release with auto-notes |

Each Skill lives at `.claude/skills/<name>/` and follows the skill-creator structure:

```
.claude/skills/<name>/
├── SKILL.md           # frontmatter (pushy description) + 10-step body + JSON output schema
├── assets/            # static workflow YAML templates per language stack
└── scripts/           # git/gh helpers the body invokes via Bash (compare_yaml, ensure_pr, …)
```

The `description:` frontmatter is the routing signal. See [`prompts/04-lint-and-test-description-v1.md`](./prompts/04-lint-and-test-description-v1.md) for the rationale on one of them.

---

## Auth & safety

### The wall

The server hard-rejects any request whose target repo doesn't match the env-allowlisted `DEMO_REPO_URL`. This is the primary safety boundary — even if the agent is jailbroken or instructed by a malicious prompt, **it cannot touch other repos** because the orchestrator refuses to clone them. Per-tool permission prompts are off (`permission_mode="bypassPermissions"`); the wall is at the request boundary, not inside the loop.

### `workflows` scope is sensitive — and we use it

The fine-grained PAT used by the demo needs four permissions on the demo repo:

| Permission | Level | Used by |
|---|---|---|
| **Contents** | Read and write | `git clone` (HTTPS with embedded token) and `git push` of the workflow file commit |
| **Workflows** | Read and write | required to commit any file under `.github/workflows/`. Distinct from Contents — GitHub treats `.github/workflows/*` as a separate, more sensitive surface |
| **Pull requests** | Read and write | `gh pr list` to check whether the demo PR exists, `gh pr create` to open it the first time |
| **Actions** | Read | `gh run list --branch <demo-branch>` to populate `workflow_runs` in the response so the UI can deep-link into a freshly-started run. The pipeline orchestrator additionally polls `gh api /repos/.../actions/runs` after pushing the release tag, so it can surface the build-and-release run URL in the same response |

`Metadata: read` is implicit on every fine-grained PAT and can't be revoked.

The **Workflows** permission is the non-trivial one: workflows can read repo secrets, so granting write means whoever holds the token can effectively exfiltrate any secret stored in the repo's Actions secrets. We mitigate by:

- Scoping the PAT to **one** repo (the demo).
- Never logging the token. The server embeds it only in the clone URL passed to `git`, and `git` strips credentials from its own remote-tracking config on clone.
- Recommending GitHub App + per-installation tokens for production. The PAT path is fine for a single-repo demo where the token holder is the same as the repo owner; for a real product where someone other than the repo owner triggers a workflow change, OAuth + a GitHub App is the right answer.

### Destructive prompts must refuse

Skills only modify `.github/workflows/`. Prompts asking for force-pushes, branch deletion, or release deletion fall outside any Skill's `description:` and the agent must produce `status: refused` with a non-empty `refused.reason`. Verifiable via the destructive preset on the live demo, or via the `safety` category in the eval harness.

---

## What I don't handle well (honest)

These limitations are not bugs to fix; they're design choices made under the time budget. I'm flagging them so reviewers don't have to find them:

1. **Idempotency depends on Claude actually running step 4.** The `python3 -c "yaml..."` semantic-compare is in `SKILL.md` body, not a host-side guard. If a future Claude version skips that step, we'd over-commit (writing identical YAML twice → second commit empty, but still a commit). Mitigation: the eval harness includes idempotency cases that would catch this regression. Better mitigation (post-v1): host-side enforcement that rejects the agent's commit if the diff is semantically empty.

2. **Both Node + Python detected → the merged workflow YAML is not byte-deterministic.** Each Skill's body says "merge two single-stack templates into one workflow file with both jobs preserved" — that merge is done by Claude, not by a deterministic templating engine. Same input could produce slightly different YAML across runs (different dict-key ordering, comment placement). Idempotency may report `updated` when nothing meaningful changed. The current demo repo is Python-only so this code path isn't exercised, which is convenient but also means the issue is not measurable end-to-end here.

3. **No execution-correctness eval.** The global routing eval (`eval/run_eval.py`) measures *which Skill* gets picked, but it doesn't verify *whether the picked Skill executed correctly* (right files written, right branch state, right JSON shape). A second per-Skill eval surface for those checks is out of scope for v1.

4. **No GitHub App / OAuth.** Single fine-grained PAT scoped to one demo repo. See the auth section above. Not a security flaw at this scale, but a real production-readiness gap.

5. **Eval set is small (21 prompts) by design.** Optimised for category coverage (single / compound / misleading) over statistical confidence. A precision figure across 12 single-trigger prompts has a non-trivial confidence interval. For "is this real progress?" you want ≥ 100 prompts.

6. **The release Skill writes a tag-triggered workflow, so smoke-testing it via the demo doesn't actually fire a run.** `workflow_runs` comes back as `[]` after creation — that's documented in the SKILL.md and in the `notes` field of the response, but it is a rougher demo than the other three.

---

## How to run

### Live demo

Use the URL at the top of this README. No local setup needed for reviewers.

### Locally

System prerequisites (the `claude-agent-sdk`'s bundled CLI runs under Node, and the Skills shell out to `gh`):

- Python 3.12+
- Node.js 20+ (the SDK spawns its bundled CLI under `node`; without it `query.initialize()` exits 1)
- `git` and `gh` (GitHub CLI)

```bash
git clone https://github.com/s8w1e2ep/cicd-skills-demo.git
cd cicd-skills-demo

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Required env vars
export GITHUB_TOKEN=ghp_...                                 # fine-grained PAT — see Auth & safety for the 4 required permissions
export DEMO_REPO_URL=https://github.com/s8w1e2ep/cicd-skills-demo

# Claude auth — set ONE of these (mutually exclusive). API key wins if both are set.
export ANTHROPIC_API_KEY=sk-ant-...                         # Console billing, charged per call
# export CLAUDE_CODE_OAUTH_TOKEN=...                        # alt: long-lived OAuth from `claude setup-token` (Pro/Max)

uvicorn server.main:app --reload --port 8000
# open http://localhost:8000
```

### Eval harness

Once the service is up (locally or on Zeabur):

```bash
python eval/run_eval.py http://localhost:8000              # full run (~10–25 min — each /run is 30–90s)
python eval/run_eval.py http://localhost:8000 --limit 3    # quick smoke
python eval/run_eval.py "$EVAL_URL" --limit 5
```

Reports land under `eval/results/<timestamp>.md`. Exit code is non-zero if `single` precision falls below 0.85 — useful for wiring this into CI on the project itself.

### Deploy to Zeabur

The repo includes `Dockerfile` + `zeabur.json`. Connect the GitHub repo on Zeabur, set the three required env vars (`ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `DEMO_REPO_URL`) as secrets, and Zeabur builds and serves on the assigned domain. `/healthz` is the configured health-check path.

---

## Repo layout

```
cicd-skills-demo/
├── .claude/
│   └── skills/             # 4 Skills (path required by claude-agent-sdk)
│       └── <name>/
│           ├── SKILL.md    # frontmatter + body + JSON output schema
│           ├── assets/     # static workflow YAML templates per stack
│           └── scripts/    # git/gh helpers (compare_yaml, ensure_pr, …),
│                           #   duplicated across all 4 Skills per skill-creator
├── server/
│   ├── main.py             # FastAPI app + endpoints (incl. SSE pipeline)
│   ├── agent_runner.py     # claude-agent-sdk wrapper, JSON extraction
│   └── static/index.html   # single-page demo UI
├── tests/                  # pytest unit tests for the server (run via `pytest`)
├── eval/
│   ├── prompts.jsonl       # 21 NL prompts × {single, compound, misleading}
│   ├── run_eval.py         # harness — calls /run, scores, writes report
│   └── results/            # markdown reports, committed
├── prompts/                # key design prompts (graders read these)
├── Dockerfile
├── zeabur.json
├── pyproject.toml
├── requirements.txt
├── spec.md                 # PRD
├── plan.md                 # architecture + tradeoffs
├── task.md                 # phase checklist
├── CLAUDE.md               # conventions for future Claude sessions
└── README.md               # this file
```

---

## Where AI helped (and where the user corrected me)

The three load-bearing AI moments are documented under [`prompts/`](./prompts/):

- **[`prompts/01-framing-corrections.md`](./prompts/01-framing-corrections.md)** — the two user pushbacks that re-architected the system. Without them, I'd have built a parallel CI runner inside Zeabur and a Python-helpers folder hiding the AI's actual contribution. This is the most honest signal of "AI collaboration quality" in this repo.
- **[`prompts/02-skill-creator-alignment.md`](./prompts/02-skill-creator-alignment.md)** — the WebFetch prompt against `anthropics/skills/skill-creator/SKILL.md` and the structural changes that came out of it (pushy descriptions, explicit JSON output template, per-skill `scripts/`).
- **[`prompts/03-sdk-discovery.md`](./prompts/03-sdk-discovery.md)** — three fetches that established two facts I could not have correctly guessed: package name (`claude-agent-sdk`, not `anthropic`) and required path (`.claude/skills/`, not `skills/`). Both with quoted citations.
- **[`prompts/04-lint-and-test-description-v1.md`](./prompts/04-lint-and-test-description-v1.md)** — annotated walk-through of the v1 description against skill-creator's "pushy" guidance. No v2 was produced — the eval scored trigger 100%, leaving nothing to revise against; the decision is documented in `06-eval-misses-analysis.md`.
- **[`prompts/05-eval-prompt-design.md`](./prompts/05-eval-prompt-design.md)** — design rationale for the 21 entries in `eval/prompts.jsonl`: category distribution (12 single / 5 compound / 4 misleading), the `purpose` field on each entry, the strict `ALL:` match rule for compound (every listed Skill must fire), and which messy-prompt patterns from skill-creator I used and which I deliberately skipped.
- **[`prompts/06-eval-misses-analysis.md`](./prompts/06-eval-misses-analysis.md)** — post-eval writeup: 100% trigger / 100% safety / 50% ambiguous, the two ambiguous misses, the trade-off introduced by the `NO_SKILL_FALLBACK_INSTRUCTION` wrapper, and why we accepted the trade rather than re-tuning.

---

## Time budget

User asked for 1–2 hours total. Scope was trimmed accordingly — see [`plan.md` §3](./plan.md) for what was cut and why. The original cuts were: no GitHub App OAuth, no live progress streaming for the demo UI, no per-skill execution-correctness eval runner, no CI for this repo's own quality gates. SSE streaming was reinstated post-v1 once the single-button pipeline made it the obvious UX (see [`server/main.py`](./server/main.py)'s `/run/cicd-pipeline` endpoint); the other three remain out of scope.

---

## Submission

- **Public Git repo** — this one (`https://github.com/s8w1e2ep/cicd-skills-demo`).
- **Zeabur URL** — top of this README.
- **`prompts/` folder** — described above.
