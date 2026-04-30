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
          (references/, scripts/, assets/), output format conventions,
          and any rules about "trigger phrases" or "pushy descriptions".
          Quote exact phrasing where possible.
```

## What changed in our design after reading

| Before reading the guidelines | After |
|---|---|
| Folder convention guessed: `template.yml.j2`, `inputs.json` | Use the official names: `assets/<name>.yml` for templates, `scripts/*.sh` for the git/gh helpers each Skill body invokes |
| `description` written like a docstring ("Sets up GitHub Actions workflow...") | "Pushy" description following the explicit guidance: skill-creator says "Claude has a tendency to undertrigger skills... please make the skill descriptions a little bit 'pushy'." Description was rewritten to start with a verb phrase, enumerate trigger contexts, and include an explicit "Use this skill whenever the user wants ... — even if they don't explicitly say 'workflow' or 'GitHub Actions'." |
| Output format: vague "return JSON" | Explicit fenced-JSON template at the end of every `SKILL.md` body, with `status` enum semantics and a no-change example. The grader's exact phrasing — "ALWAYS use this exact template" — is followed. |
| Routing eval: nothing | Project-level `eval/prompts.jsonl` (21 entries: 12 single / 5 compound / 4 misleading) scored by `eval/run_eval.py`. skill-creator mentions writing test prompts but does not prescribe a per-Skill `evals/` folder, so we use a single project-level surface. |
| `SKILL.md` was a long, unstructured document | Strict body sections: When to use, Scripts, Steps, Output format. Body kept well under the 500-line target. |
| Considered using `references/` | Rejected: SKILL.md fits comfortably in budget without paging documentation. Adding `references/` for a 100-line body is indirection without value. |

## A correction we shipped later

An earlier version of this file also claimed each Skill should have an `evals/evals.json` following an "official schema." That was a misread on my part — skill-creator's structure section lists three optional folders (`scripts/`, `references/`, `assets/`), no `evals/`. We had four `evals/evals.json` files for a while; they conformed to no consumer (neither our routing eval nor any harness used them) and they padded the Skill folders past what skill-creator specifies. They were deleted in a follow-up cleanup pass.

A separate trade-off in the same pass: the four `scripts/*.sh` helpers had been *centralised* under `.claude/scripts/` for DRY. We rolled that back to per-Skill `scripts/` directories — strict skill-creator conformance over DRY. The cost is four byte-identical copies a fix has to be applied to; the benefit is that each Skill folder is self-contained and could be lifted into another repo as-is.

## What I deliberately did NOT change

- Skipped `references/` even though it's in the official structure. SKILL.md is short enough; paging out wouldn't earn its complexity.
- Did not enable `compatibility:` frontmatter. The README says it's "rarely needed."
