# CLAUDE.md — task1-cicd-skills

This file gives future Claude Code sessions the context to keep working on this project without re-deriving conventions from scratch.

## What this project is

A submission for **Task 1** of an AI Coding Test: package common GitHub CI/CD workflows into reusable **Claude Skills** (idiomatic per the official skill-creator guidelines), expose them through a **FastAPI demo service** deployed on **Zeabur**, and provide an **eval set** that measures whether Skill descriptions trigger Claude precisely.

**Key framing — do not lose this:**

- A Skill's job is to **author / update a `.github/workflows/*.yml` file in the current repo, then commit + push + ensure PR**.
- The Skill does NOT execute CI tasks itself — GitHub Actions does that.
- Skills are **idiomatic Claude Skills** — markdown instructions Claude follows using its native Read / Write / Bash tools. They are not Python programs wearing a SKILL.md hat.
- The Zeabur service is a thin orchestrator: clone demo repo → launch Claude Agent SDK with the skills loaded → parse Claude's final JSON output block → return.

The four Skills:

1. `lint-and-test` → `.github/workflows/lint-and-test.yml`
2. `dependency-audit` → `.github/workflows/dependency-audit.yml`
3. `security-scan` → `.github/workflows/security-scan.yml`
4. `build-and-release` → `.github/workflows/release.yml`

All four push to a single shared branch `claude/ci-demo` on the demo repo, with a single persistent PR back to `main`.

## Layout

```
task1-cicd-skills/
├── skills/                       # one directory per Skill (idiomatic per skill-creator)
│   └── <name>/
│       ├── SKILL.md              # frontmatter (pushy description) + body (< 500 lines)
│       ├── assets/               # workflow YAML templates per language stack
│       │   └── *.yml
│       └── evals/
│           └── evals.json        # per-skill execution evals
├── server/
│   ├── main.py                   # FastAPI: /run, /run/skill/{name}, /healthz, /
│   └── static/index.html         # single-page demo UI
├── eval/
│   ├── prompts.jsonl             # global routing eval (NL prompts → expected_skill)
│   ├── run_eval.py               # scores trigger precision per category
│   └── results/                  # markdown reports, committed
├── prompts/                      # key prompts that shaped design (graders read these)
├── Dockerfile
├── zeabur.json                   # Zeabur runtime config
├── README.md
├── spec.md                       # PRD
├── plan.md                       # architecture + tradeoffs
└── task.md                       # ordered task checklist
```

Note: there is **no global `helpers/` or `scripts/`**. Skills do not share custom Python utilities — each Skill is self-contained markdown + assets. The only "code" Claude executes is via inline `python3 -c …` one-liners (e.g., for semantic YAML compare) and `gh` / `git` shell commands, both of which appear directly in SKILL.md.

## Conventions (reflecting skill-creator guidelines)

- **Pushy descriptions.** The `description:` frontmatter is the routing signal. Per skill-creator: "Claude has a tendency to undertrigger skills." Descriptions must include both WHAT the skill does and WHEN to use it, with a sentence like "Use this even if the user doesn't explicitly say <X>".
- **Three-level progressive disclosure.** Metadata always in context (description), SKILL.md body loaded on trigger (< 500 lines), bundled resources (`assets/`) loaded on demand by Read.
- **Imperative steps, explain why.** Steps are imperative ("Read X", "Run command Y"); for non-obvious requirements, explain the reasoning. Avoid excessive ALWAYS/NEVER caps.
- **Templates are deterministic.** Files in `assets/` are static — no timestamps, no run-IDs, no random values. Same template → byte-identical output. Idempotency depends on this.
- **Idempotency check is in SKILL.md, not in code.** Each Skill's body includes the exact `python3 -c "import yaml; …"` command for semantic comparison, with explicit handling for SAME (skip + return `no_change`) and DIFF (continue).
- **Output format is explicit.** Every SKILL.md ends with the JSON output schema and an instruction "Do not add prose after the JSON block." Server parser takes the LAST JSON block in stdout.
- **Single shared branch.** All four Skills push to `claude/ci-demo`. Never per-Skill branches. Never force-push.
- **Single persistent PR.** Created on first run, kept open thereafter, `gh pr create` is a no-op if it already exists.
- **Repo allowlist is the safety wall.** Server rejects any `repo_url` that doesn't match `DEMO_REPO_URL` env. Even if the agent is jailbroken, it cannot touch other repos.
- **Read-only outside `.github/workflows/`.** No Skill modifies anything else. Destructive actions (delete branch, force push, remove workflow) are NOT Skills — Claude must produce `status: refused` with a reason.
- **Commit hygiene.** Small, intent-revealing commits. The grader reads commit history. Do not squash; do not force-push.
- **Prompt logging discipline.** When a prompt materially shapes a design decision, save it under `prompts/<area>/` with a one-line header.

## Things NOT to do

- Don't add a fifth Skill until the four above are solid + evaluated.
- Don't introduce a global `helpers/` or `scripts/` folder. Each Skill is self-contained.
- Don't include non-YAML files (`dependabot.yml`, `.semgrep.yml`, etc.) in v1.
- Don't open fresh PRs per run; update the existing `claude/ci-demo` PR.
- Don't force-push the demo branch.
- Don't put timestamps / run-IDs / nonces in templates.
- Don't write SKILL.md descriptions that are timid or context-free — they will undertrigger.
- Don't `git push --force` on this repo, don't amend pushed commits.

## Time budget

User wants this in 1–2 hours total. Scope has been trimmed accordingly — see `plan.md` §3 for what was cut and why. Resist re-expanding scope.

## Reference

- Official skill-creator guidelines: https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md
- Claude Code Skills docs: https://code.claude.com/docs/en/skills
