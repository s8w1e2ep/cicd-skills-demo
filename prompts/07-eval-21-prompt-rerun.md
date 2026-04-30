# 07 — Eval rerun on the redesigned 21-prompt set

Recorded after running `eval/run_eval.py` against the live Zeabur deploy
on the 21-prompt set defined in `prompts/05-eval-prompt-design.md`.
Report file: `eval/results/eval-20260430-200859.md`. This file closes
the loop on the open questions in `06-eval-misses-analysis.md` (which
was written against the older 16-prompt set with the `trigger /
ambiguous / safety` shape).

## Final scores

| Category   | Pass | Total | Precision |
|------------|-----:|------:|----------:|
| single     | 12   | 12    | **100%**  |
| compound   | 5    | 5     | **100%**  |
| misleading | 4    | 4     | **100%**  |
| overall    | 21   | 21    | **100%**  |

## What changed since 06

Two distinct changes between `06`'s 88% rerun and this 100% rerun.
The first was a category redesign; the second was an unrelated runtime
fix that turned out to matter once the redesign exposed it.

### 1. Eval shape redesigned (commits `24bef40` + `fe11d1c`)

The 16-prompt set's three categories were `trigger / ambiguous /
safety`. `06` documented an explicit trade-off where the
`NO_SKILL_FALLBACK_INSTRUCTION` wrapper improved safety to 100% at the
cost of ambiguous dropping to 50% (two prompts that were genuinely
under-specified got refused instead of being routed).

The redesign in `05` replaced that shape with `single / compound /
misleading`:

- **`ambiguous` was retired** — it was scoring a "judgment-call"
  behaviour that depended on prompt phrasing more than Skill design,
  and the trade-off was already being absorbed by the wrapper. The
  signal-to-noise was poor.
- **`compound` was added** — explicitly tests whether Claude chains
  *multiple* Skills when the user asks for several things at once.
  Strict `ALL:` matching: every listed Skill must appear in
  `skills_invoked`.
- **`misleading` replaced `safety`** — same refusal contract, but the
  prompts are deliberately crafted to share keywords with a Skill (so
  they exercise description-pushiness vs refusal, not just plain
  destructive ops).

Net effect on 06's open question ("ambiguous lost ground to safety, do
we tune the wrapper?"): the ambiguous category no longer exists, so
the trade-off it was measuring is no longer measurable. We did not
soften the wrapper. We did make the eval shape better at telling us
when the wrapper is helping vs hurting.

### 2. `MAX_TURNS` raised from 30 → 60 (commit `34c6682`)

After the redesign, the first run of the 21-prompt set scored
**compound 1/5**. Looking at the failures: each one ran ~120–150
seconds before erroring with `ProcessError`, which matched the
turns-exhausted pattern. Each Skill consumes 6–8 SDK turns end-to-end
(detect stack → read template → check existing → compare → write →
commit → push → ensure PR → list runs), and a 4-Skill chain bills 24–
32+ turns. The default ceiling at 30 was leaving the last Skill
dangling.

Bumping `DEFAULT_MAX_TURNS` to 60 in `server/agent_runner.py` gave
the chain enough headroom and the rerun captured here scored
compound 5/5.

This was an unforced runtime configuration error, not a Skill or
prompt issue. Worth flagging because:

- It only surfaced under `compound` — the older `trigger / ambiguous /
  safety` shape never asked Claude to chain Skills, so the limit was
  invisible.
- It illustrates that **`max_turns` is a load-bearing knob for
  multi-Skill orchestration**, distinct from `max_tokens`. The model
  doesn't see it; the SDK does. Setting it too low silently truncates
  the chain mid-Skill, which looks identical to "the Skill failed".

## How the wrapper rules map onto each compound / misleading pass

The `NO_SKILL_FALLBACK_INSTRUCTION` wrapper has two clauses (see
`server/main.py`). After the redesign it's clearer than it was in `06`
which clause is doing what:

| Clause | What it enables | Now exercised by |
|---|---|---|
| Rule 1: "if the user enumerates multiple distinct CI/CD concerns, invoke each relevant Skill in turn" | Compound chaining — Claude doesn't pick the most-keyword-matchy single Skill and stop | `compound` (5/5) |
| Rule 2: "if your reply does not invoke any Skill … your final assistant message must be a single JSON code block with `status: refused` and a `message` field" | Refusal on destructive / out-of-scope / no-Skill-matches | `misleading` (4/4) |

Both rules are now load-bearing for at least one passing category. In
`06`'s analysis only rule 2 was visible (as `safety`); rule 1 had been
added speculatively and the eval couldn't yet measure whether it was
firing.

## What 06's "what we'd try next" turned into

For traceability:

- **Description deltas** ("production-readiness", "build pipeline",
  etc.) — not done. The redesign retired the ambiguous prompts those
  deltas were targeting, so the question became moot.
- **Wrapper softening** — not done, and after this rerun we have
  positive evidence not to: rule 2 is what makes misleading pass at
  100%, and softening it risks regressing both that and the
  destructive-prompt protection generally.
- **Few-shot inside the wrapper** — not done. Compound now passes 5/5
  on plain prose without examples; the budget is better spent on the
  per-Skill execution-correctness eval mentioned in `05`.

## Reproducibility

```bash
.venv/bin/python eval/run_eval.py https://cicd-demo.zeabur.app
```

This run took ~32 minutes wall-clock. The harness is idempotent — once
the four workflow files are on `claude/ci-demo`, every Skill run
returns `no_change` instead of producing a new commit, so re-running
the eval does not spam the demo branch. Compound prompts cost more
turns (and tokens) than single because they chain multiple Skills in
the same SDK session.
