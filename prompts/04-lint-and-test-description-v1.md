# 04 — `lint-and-test` description: v1 rationale

The most important string in this whole project is the YAML `description:` field of `lint-and-test/SKILL.md`. It's what Claude reads to decide *whether* to invoke the skill from a natural-language prompt — the `trigger precision` scoring axis hinges on this string. This file explains the choices in the v1 text and what I'd watch for when revising it after the eval harness runs.

## v1 (current)

```yaml
description: Set up a GitHub Actions workflow that runs lint and unit
  tests on every push and pull request, for a Node or Python repo.
  Detects the language stack from package.json / pyproject.toml
  automatically. Use this skill whenever the user wants CI for tests,
  linting, type-checking, code style enforcement, build verification,
  or "make sure the tests pass before merge" — even if they don't
  explicitly say "workflow" or "GitHub Actions". Do not use for
  dependency CVE scanning, secret scanning, or release automation —
  defer to the sibling skills for those.
```

## Annotated against skill-creator guidance

| Line | Why it's there |
|---|---|
| "Set up a GitHub Actions workflow..." | Verb-phrase opening — skill-creator's example structure ("How to build a simple fast dashboard..."). Tells Claude *what the skill does* in the first eight words. |
| "...runs lint and unit tests on every push and pull request" | Concrete behavior, not just a name. Helps disambiguate from sibling skills (release / scan workflows). |
| "...for a Node or Python repo" | Stack scope: keeps Claude from invoking on languages we don't support. The SKILL.md body matches this and refuses if neither stack is detected. |
| "Detects the language stack from package.json / pyproject.toml automatically" | Tells Claude that *no input parameters are needed* — important because the user said inputs should be implicit. Without this, Claude might ask the user to specify the language. |
| "Use this skill whenever the user wants CI for tests, linting, type-checking, code style enforcement, build verification, or 'make sure the tests pass before merge'" | This is the **trigger phrase enumeration**. Six explicit triggers covering common phrasings. The list is wider than the skill name strictly suggests because real prompts use varied vocabulary. |
| "...even if they don't explicitly say 'workflow' or 'GitHub Actions'" | The "pushy" line per skill-creator's guidance. Combats Claude's tendency to undertrigger when the user's prompt doesn't include the literal noun. |
| "Do not use for dependency CVE scanning, secret scanning, or release automation — defer to the sibling skills for those" | Explicit non-trigger boundaries. Skill-creator doesn't require this, but it's load-bearing for the trigger-precision eval: ambiguous prompts like "is this safe to ship?" need to land on `security-scan` or `dependency-audit`, not here. The sentence reads as guard-rail for Claude. |

## What v2 will care about (after the eval harness runs)

The eval set has eight `trigger` cases, four `ambiguous` cases, three `safety` cases. For v1 → v2 to be a meaningful revision, I want measured numbers from the harness:

| Failure mode if v1 misses | Description-level fix |
|---|---|
| `lint-and-test` fires on "scan for vulnerabilities" | Strengthen the *non-trigger* clause; consider negative trigger phrases ("...do not use when the user says 'scan', 'vulnerability', 'CVE', 'audit'") |
| `lint-and-test` fails to fire on "I want red Xs in PRs when tests fail" | Add this exact phrasing to the trigger list. Real users describe outcomes, not artifacts. |
| `lint-and-test` fires on "set up the build pipeline" *and* `build-and-release` also fires | Sharpen the verb separation: this skill is about *running* tests, not *producing artifacts* |
| `lint-and-test` doesn't fire on TypeScript repos | The "Node" wording covers TS via package.json detection in the body, but the description should mention TypeScript explicitly |

I'll only revise once we have the numbers — see [README.md](./README.md) for why v2 is deferred to `05-*`.

## Anti-patterns I deliberately avoided

- **Naming the underlying actions/marketplace tools.** "actions/setup-node@v4" or "actions/setup-python@v5" doesn't help the model decide whether to *invoke*; it leaks template detail into the trigger surface.
- **Conditional language ("if your repo has tests")**. The skill *creates* the workflow; the workflow itself runs against tests-or-not. The description should describe behavior, not preconditions Claude can't verify from the prompt.
- **Capitalised imperatives ("USE THIS WHEN...")**. skill-creator explicitly flags this: *"If you find yourself writing ALWAYS or NEVER in all caps, or using super rigid structures, that's a yellow flag."* The "even if they don't explicitly say" phrasing carries the same intent without the shouting.
