# 01 — Framing corrections

The two highest-signal moments in this project were not prompts that produced code; they were prompts where the user pushed back on the framing I had locked into. Both of them changed the architecture, not just an implementation detail.

## Correction A — "Skill produces YAML; GitHub Actions executes"

After I'd written the first version of `spec.md` / `plan.md`, my mental model was that **the Skill was the runner**: it would shell out to `pytest`, `gitleaks`, etc. inside the Zeabur container. The user's prompt:

> 我理解的作業一 demo，是透過 skills 去產生 demo repo 內的 github CI/CD action workflow，再由 github runner 去執行，跟你想像中的 demo 有點不一樣，想先同步我們之間的理解與共識

What this changed:

- **Skill responsibility flipped.** Before: clone repo, run lint/test, parse output. After: read repo, render `.github/workflows/*.yml`, commit, push, ensure PR.
- **`build-and-release` from "real release with confirm token" → "produce release.yml workflow file".**
- **Demo repo seeding flipped.** Before: plant CVEs, lint errors, fake secrets so the running Skill produces interesting output. After: keep repo lean so each Skill has YAML to add.
- **Idempotency story sharpened.** The naïve version ("don't re-clone, don't re-download") became something with real teeth: "read existing YAML, semantic-diff, skip if equal." This idempotency mechanism is now the most-tested behavior in the project.
- **The four scoring axes (Skill boundaries, auth/safety, idempotency, trigger precision) all became more meaningful.** Especially `auth/safety`: it's now about the sensitive `workflows` PAT scope, not generic shell allowlisting.

This is the correction that put the project on the right track. Without it, I would have built a parallel-universe CI runner inside Zeabur — a category error.

## Correction B — "Skills are pure markdown; helpers were over-engineering"

I had proposed a `server/helpers/` folder containing five Python scripts (`clone_demo_repo.py`, `commit_or_skip.py`, `ensure_pr.py`, etc.) that the Skills would call. The user's prompt:

> 我對於 helpers 這段不是很了解，我原本預期的是透過 claude code 去使用 ci/cd 的 skills，並產出對應的 yaml 檔案

What this changed:

- **Helpers folder deleted in design before it was written in code.** This saved roughly a third of the Phase 1–2 work.
- **Skills became idiomatic.** The folder structure now matches what the official `skill-creator` skill specifies: `SKILL.md` + `assets/` + `scripts/`. No surprise structure.
- **Idempotency moved from a Python program into a single instruction in `SKILL.md`** — a one-line `python3 -c "import yaml; ..."` semantic-compare command. The body of the Skill carries it; the runner doesn't.
- **AI-collaboration evidence is now legible.** With helpers, the answer to "where did the AI work?" was diluted across server-side code and Skill content. With pure-markdown Skills, the AI's contribution lives entirely in the descriptions and the body instructions — which is what the test grades.

I rationalised the helpers as "engineering rigor for idempotency." The user correctly pointed out that the rigor was misplaced: idempotency belongs at the git layer (semantic-equal check before committing), not in a parallel codebase that competes with the Skill body for who-is-the-source-of-truth.

## What I take from this

Both corrections shared the same shape: I'd added a layer of indirection ("server runs the CI", "helpers run the git ops") that solved an imagined problem and obscured the actual one. The user's pushback in both cases was a one-paragraph reframing — short, but load-bearing. The right thing to do is read these prompts twice and fold them into the spec immediately, not argue or seek a hybrid.
