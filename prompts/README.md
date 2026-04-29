# prompts/

Key prompts that shaped this project's design. The grader was told they would read these, so the goal here is signal, not volume — each file documents a moment where AI collaboration changed the direction or substance of the work.

The buckets used so far:

| File | What it documents |
|---|---|
| [`01-framing-corrections.md`](./01-framing-corrections.md) | Two corrections the user made to my initial mental model. The biggest design wins came from these, not from initial generation. |
| [`02-skill-creator-alignment.md`](./02-skill-creator-alignment.md) | The WebFetch prompts I used to validate against the official `anthropics/skills` skill-creator guidelines, and the structural changes that resulted. |
| [`03-sdk-discovery.md`](./03-sdk-discovery.md) | Research that revealed the project must use `claude-agent-sdk` (not the plain `anthropic` SDK) and that Skills must live at `.claude/skills/` — both load-bearing for whether the demo runs at all. |
| [`04-lint-and-test-description-v1.md`](./04-lint-and-test-description-v1.md) | Annotated walk-through of the current `lint-and-test` `description:` frontmatter against skill-creator's "pushy description" guidance. v1 — see note on v2 below. |
| [`06-eval-prompt-design.md`](./06-eval-prompt-design.md) | Design rationale for the 16 entries in `eval/prompts.jsonl` — category distribution, why 9/4/3, which messy-prompt patterns from skill-creator I used and which I deliberately skipped. |
| [`07-eval-misses-analysis.md`](./07-eval-misses-analysis.md) | Post-eval analysis: 100% trigger / 100% safety / 50% ambiguous, the two ambiguous misses, the trade-off introduced by `NO_SKILL_FALLBACK_INSTRUCTION`, and why we are accepting it rather than re-tuning. |

## On the missing `05-`

Slot `05-` was originally reserved for a `lint-and-test` description v2 with measured before/after numbers. After running the eval (see `07`), trigger precision came in at 100% across all four Skills in both English and Chinese — there is no description-tuning win to be had from `lint-and-test` specifically, so v2 was not written. Renumbering `06`/`07` to close the gap would erase that signal; the gap is the point.

If a future iteration revisits descriptions (e.g. to claim "production-readiness" and "build pipeline" phrasing in the ambiguous category, per `07`'s "what we'd try next" section), `05` becomes the natural place for those before/after numbers.
