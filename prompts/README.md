# prompts/

Key prompts that shaped this project's design. The grader was told they would read these, so the goal here is signal, not volume — each file documents a moment where AI collaboration changed the direction or substance of the work.

The buckets used so far:

| File | What it documents |
|---|---|
| [`01-framing-corrections.md`](./01-framing-corrections.md) | Two corrections the user made to my initial mental model. The biggest design wins came from these, not from initial generation. |
| [`02-skill-creator-alignment.md`](./02-skill-creator-alignment.md) | The WebFetch prompts I used to validate against the official `anthropics/skills` skill-creator guidelines, and the structural changes that resulted. |
| [`03-sdk-discovery.md`](./03-sdk-discovery.md) | Research that revealed the project must use `claude-agent-sdk` (not the plain `anthropic` SDK) and that Skills must live at `.claude/skills/` — both load-bearing for whether the demo runs at all. |
| [`04-lint-and-test-description-v1.md`](./04-lint-and-test-description-v1.md) | Annotated walk-through of the current `lint-and-test` `description:` frontmatter against skill-creator's "pushy description" guidance. v1 only — no v2 was needed; see `06` for why. |
| [`05-eval-prompt-design.md`](./05-eval-prompt-design.md) | Design rationale for the 20 entries in `eval/prompts.jsonl` — category distribution (12 single / 4 compound / 4 misleading), the `purpose` field on each entry, and which messy-prompt patterns from skill-creator I used and which I deliberately skipped. |
| [`06-eval-misses-analysis.md`](./06-eval-misses-analysis.md) | Earlier post-eval analysis (16-prompt run): the two ambiguous misses, the trade-off introduced by `NO_SKILL_FALLBACK_INSTRUCTION`, and why we accepted it rather than re-tuning. The eval set was redesigned afterwards (see `05`); this file captures what we learnt before that. |
