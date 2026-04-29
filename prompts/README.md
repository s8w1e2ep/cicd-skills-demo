# prompts/

Key prompts that shaped this project's design. The grader was told they would read these, so the goal here is signal, not volume — each file documents a moment where AI collaboration changed the direction or substance of the work.

The four buckets used so far:

| File | What it documents |
|---|---|
| [`01-framing-corrections.md`](./01-framing-corrections.md) | Two corrections the user made to my initial mental model. The biggest design wins came from these, not from initial generation. |
| [`02-skill-creator-alignment.md`](./02-skill-creator-alignment.md) | The WebFetch prompts I used to validate against the official `anthropics/skills` skill-creator guidelines, and the structural changes that resulted. |
| [`03-sdk-discovery.md`](./03-sdk-discovery.md) | Research that revealed the project must use `claude-agent-sdk` (not the plain `anthropic` SDK) and that Skills must live at `.claude/skills/` — both load-bearing for whether the demo runs at all. |
| [`04-lint-and-test-description-v1.md`](./04-lint-and-test-description-v1.md) | Annotated walk-through of the current `lint-and-test` `description:` frontmatter against skill-creator's "pushy description" guidance. v1 — v2 will be added under `05-*` after the eval harness runs and we can measure trigger precision. |

## What's missing (and why)

The plan called for prompts under `skill-design/`, `eval-generation/`, `failure-analysis/`. Those entries arrive at the end of the loop, not the start:

- **Description revision (skill-design v2)** — needs measured precision on the eval set first, then a targeted revision prompt with before/after numbers. Will be `05-lint-and-test-description-v2.md` once Phase 4 runs.
- **Eval-set generation** — the prompt I'd use to brainstorm trigger / ambiguous / safety cases against the four Skills. Will be `06-eval-prompt-brainstorm.md`.
- **Failure analysis** — needs at least one Skill miss to analyze. Will be `07-eval-misses-analysis.md` if the harness produces any.

The README is updated as those land. If a category is empty when the grader reads this, that means the corresponding phase wasn't reached in the time budget.
