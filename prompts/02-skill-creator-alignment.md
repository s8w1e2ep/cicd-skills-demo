# 02 — Aligning with the official skill-creator

The user pointed me at the official skill-creator guidelines:

> 請參考官方 skill creator 的準則，並定義好輸出的格式，若內容太多，可以使用 references 去拆分

I fetched the canonical source rather than work from memory.

## The fetch

```
WebFetch
  url:    https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md
  prompt: Extract the complete guidelines for creating a Skill: required
          frontmatter fields, description writing rules, when to use
          references vs inline content, recommended folder structure
          (references/, scripts/, assets/, evals/), output format
          conventions, and any rules about "trigger phrases" or "pushy
          descriptions". Quote exact phrasing where possible.
```

## What changed in our design after reading

| Before reading the guidelines | After |
|---|---|
| Folder convention guessed: `template.yml.j2`, `inputs.json` | Use the official names: `assets/<name>.yml`, `evals/evals.json` |
| `description` written like a docstring ("Sets up GitHub Actions workflow...") | "Pushy" description following the explicit guidance: skill-creator says "Claude has a tendency to undertrigger skills... please make the skill descriptions a little bit 'pushy'." Description was rewritten to start with a verb phrase, enumerate trigger contexts, and include an explicit "Use this skill whenever the user wants ... — even if they don't explicitly say 'workflow' or 'GitHub Actions'." |
| Output format: vague "return JSON" | Explicit fenced-JSON template at the end of every `SKILL.md` body, with `status` enum semantics and a no-change example. The grader's exact phrasing — "ALWAYS use this exact template" — is followed. |
| `evals/` was a single project-level `prompts.jsonl` | Two layers: per-skill `evals/evals.json` (skill execution correctness) plus project-level `eval/prompts.jsonl` (routing precision). Per-skill evals follow the official schema (`skill_name`, `evals[].id`, `prompt`, `expected_output`, `files`). |
| `SKILL.md` was a long, unstructured document | Strict body sections: When to use, Steps, Idempotency check, Output format. Body kept under 200 lines well within the 500-line target. |
| Considered using `scripts/` and `references/` | Rejected for v1: SKILL.md is short enough, and the only "deterministic" code (semantic YAML compare) fits inline as a `python3 -c …` one-liner. Adding `scripts/` would have re-introduced the helpers anti-pattern from `01-framing-corrections.md`. |

## What I deliberately did NOT change

- Skipped `scripts/` and `references/` folders even though they are in the official structure. Both are optional, and using them when SKILL.md is already short would have added indirection without value.
- Did not enable `compatibility:` frontmatter. The README says it's "rarely needed."

## What this implies for v2

When the eval harness measures trigger precision, the description language is the lever. skill-creator's guidance on "pushy" wording is a starting heuristic — the empirical test is whether `lint-and-test`'s description correctly fires on prompts like "is this safe to ship?" (it shouldn't — that's `security-scan`'s territory). If precision is below the 0.85 target, this is the file to revise, not the body or the templates.
