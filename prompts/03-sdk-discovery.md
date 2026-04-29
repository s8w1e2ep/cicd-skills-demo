# 03 — SDK discovery

Two facts about the runtime were not in my training memory and could have silently broken the demo if I'd guessed. Both came from research, not memory.

## Fact 1 — the package is `claude-agent-sdk`, not `anthropic`

After invoking the `claude-api` skill for SDK guidance, the bundled docs covered the regular `anthropic` SDK and Managed Agents (server-hosted). Neither was the right fit:

- The `anthropic` SDK gives me raw Messages API access. To use it for this project, I'd have to reimplement Skill discovery, the `Skill` meta-tool, and the Read/Write/Bash tool surface. Plausible but a lot of code.
- Managed Agents would have Anthropic host the agent loop and the tool-execution sandbox. Skills attach via the Skills API (uploaded as objects), not via local `.claude/skills/` files. Wrong fit for a "Skills as filesystem artifacts" deliverable.

The right answer was the standalone **Claude Agent SDK** (Python package: `claude-agent-sdk`). I confirmed this with one search:

```
WebSearch
  query: claude-agent-sdk python package install ClaudeSDKClient skills loading 2026
```

This surfaced the PyPI listing and the official docs. Key finding: it bundles the Claude Code CLI internally, so no Node.js dependency in the Dockerfile. I confirmed that bundled-CLI claim with a second fetch:

```
WebFetch
  url:    https://github.com/anthropics/claude-agent-sdk-python
  prompt: Quote exactly the install instructions and prerequisites: does
          the Python claude-agent-sdk require Node.js / @anthropic-ai/
          claude-code CLI to be installed alongside? What env vars does
          it read? Quote the README "Prerequisites" or "Installation"
          section verbatim.
```

The README was unambiguous: *"The Claude Code CLI is automatically bundled with the package — no separate installation required."* That cut a layer of Dockerfile complexity (no Node, no `npm install -g @anthropic-ai/claude-code`).

## Fact 2 — Skills must live at `.claude/skills/`, not `skills/`

This one was load-bearing. We had already written `skills/lint-and-test/SKILL.md`. Two more fetches established that the SDK looks for Skills under `.claude/skills/` and only when `setting_sources` includes `"project"`:

```
WebFetch
  url:    https://code.claude.com/docs/en/agent-sdk/skills
  prompt: Extract the complete Python API for loading and using Skills
          with claude-agent-sdk: the exact ClaudeAgentOptions fields
          needed (setting_sources, cwd, allowed_tools, system_prompt,
          permission_mode, model), the directory structure the SDK
          expects (.claude/skills/ vs project skills/), how to invoke
          a query and receive the message stream, how to detect the
          final assistant message text, and any caveats about how
          Skills are auto-discovered vs explicitly listed.
```

Two specific findings from this:

- *"The SDK loads Skills relative to the cwd option. Ensure it points to a directory containing `.claude/skills/`."*
- *"Skills not loaded: `setting_sources` excludes user and project. Skills loaded: user and project sources included."*

Both quoted directly from the docs. The implication for our code is exact: `cwd` must be set to the scratch clone, AND `setting_sources` must include `"project"`. Either alone is silent failure.

```
WebFetch
  url:    https://code.claude.com/docs/en/agent-sdk/python
  prompt: Extract the Python claude-agent-sdk reference: the query()
          function signature, ClaudeAgentOptions full field list
          (permission_mode values, model, system_prompt, allowed_tools,
          cwd, setting_sources), the message types yielded by the async
          iterator (AssistantMessage, UserMessage, ResultMessage) and
          how to extract assistant text content from them.
```

This gave me the exact Python types (`AssistantMessage`, `TextBlock`, `ResultMessage`) and the iteration pattern that `agent_runner.py` now uses verbatim.

## Action taken

- `git mv skills .claude/skills` (preserves history; one commit).
- Updated all four planning docs (CLAUDE.md, spec.md, plan.md, task.md) to reference the new path.
- Added the explicit reasoning in spec.md §4.2 so anyone reading the docs without the conversation context understands *why* the path is what it is.

## What this teaches

Two of the most consequential design choices in this project — package selection and folder layout — were dictated by SDK behavior I could not have correctly guessed. The cost of one WebFetch (under a minute) was an order of magnitude smaller than the cost of debugging a silent "Skills not loading" error post-deploy on Zeabur. When the project hinges on a third-party SDK's exact contract, look it up.
