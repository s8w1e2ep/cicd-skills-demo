# prompts/

Key prompts that shaped this project's design. The grader was told they would read these, so the goal here is signal, not volume — each file documents a moment where AI collaboration changed the direction or substance of the work.

The buckets used so far:

| File | What it documents |
|---|---|
| [`01-framing-corrections.md`](./01-framing-corrections.md) | Two corrections the user made to my initial mental model. The biggest design wins came from these, not from initial generation. |
| [`02-skill-creator-alignment.md`](./02-skill-creator-alignment.md) | The WebFetch prompts I used to validate against the official `anthropics/skills` skill-creator guidelines, and the structural changes that resulted. |
| [`03-sdk-discovery.md`](./03-sdk-discovery.md) | Research that revealed the project must use `claude-agent-sdk` (not the plain `anthropic` SDK) and that Skills must live at `.claude/skills/` — both load-bearing for whether the demo runs at all. |
| [`04-lint-and-test-description-v1.md`](./04-lint-and-test-description-v1.md) | Annotated walk-through of the current `lint-and-test` `description:` frontmatter against skill-creator's "pushy description" guidance. v1 — v2 follows the eval run. |
| [`06-eval-prompt-design.md`](./06-eval-prompt-design.md) | Design rationale for the 16 entries in `eval/prompts.jsonl` — category distribution, why 9/4/3, which messy-prompt patterns from skill-creator I used and which I deliberately skipped. |

## What's missing (and why)

Two slots are reserved for entries that genuinely cannot be written until after a real eval run:

- **`05-lint-and-test-description-v2.md`** — the v1 → v2 description revision with measured before/after precision. Needs the `eval/run_eval.py` harness to run against the live Zeabur URL first, which is currently blocked on the deploy 502 (see Phase 7 in [`task.md`](../task.md)). Without measured numbers, a "v2" would be a guess and would defeat the purpose of having a v2.
- **`07-eval-misses-analysis.md`** — root-cause analysis of any prompts the harness scored as misses. Equally blocked on the eval run; equally pointless to fabricate.

If those two slots are empty when you read this, the deploy fix is still pending. The README and `task.md` document the current state.
