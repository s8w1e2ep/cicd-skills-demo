"""Wraps claude-agent-sdk for the CI/CD Skills demo.

The runner is invoked once per request:
  1. Caller hands us a scratch clone of the demo repo + the user's prompt.
  2. We launch claude_agent_sdk.query() with cwd pinned to the scratch dir
     and setting_sources=["project"] so Skills load from
     <scratch>/.claude/skills/.
  3. We collect the assistant message stream, keeping the most recent
     assistant text block (Skills are instructed to emit a single JSON
     code block as the final response content).
  4. We parse the last fenced JSON block and return it alongside metadata.

Idempotency, branch handling, and PR creation all happen inside the Skill
body — the runner does not inspect or post-process the agent's git ops.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

# Default tool surface for our Skills. "Skill" is the meta-tool that lets
# Claude invoke a SKILL.md by name; the rest are the standard file/shell tools
# the Skills bodies depend on.
DEFAULT_ALLOWED_TOOLS = [
    "Skill",
    "Read",
    "Write",
    "Edit",
    "Bash",
    "Grep",
    "Glob",
]

# Hard cap on how many SDK turns one /run call can consume. A single Skill
# typically converges in 6-8 turns; the older 30-turn ceiling fit a 1-2 Skill
# session comfortably but ran out of room when a compound prompt asked Claude
# to chain three or four Skills end-to-end (~24-32 turns just for the Skills,
# plus inter-Skill transitions). The 21-prompt eval scored 4 ALL: compound
# prompts as 502 ProcessError, with each call burning ~120-150s before
# erroring — exactly the shape of "all turns consumed."
#
# 60 covers a 4-Skill chain with margin. The cap still bounds runaway loops:
# a Skill that genuinely cannot converge in 60 turns is broken regardless.
# /run/cicd-pipeline runs each forced Skill in its own session, so it never
# bumps against this cap; this lift is for the free-form /run path's compound
# prompts.
DEFAULT_MAX_TURNS = 60


@dataclass
class AgentResult:
    parsed: dict[str, Any] | None
    raw_final_text: str
    duration_s: float
    num_turns: int | None
    cost_usd: float | None
    parse_error: str | None = None
    transcript: list[str] = field(default_factory=list)
    # The bundled CLI's stderr — by default the SDK inherits the parent fd and
    # bakes a placeholder string ("Check stderr output for details") into any
    # ProcessError it raises, which means callers see no actual error content.
    # Capturing via the stderr callback lets us surface real diagnostics.
    stderr_lines: list[str] = field(default_factory=list)
    # Every distinct Skill name that emitted a JSON output block during the
    # run, in invocation order. Compound prompts ("set up tests AND security
    # AND release") can chain multiple Skills, so the eval scorer needs the
    # full set rather than just the last block's `skill` field.
    skills_invoked: list[str] = field(default_factory=list)


_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```",
    re.DOTALL,
)


def _extract_last_json(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """Pull the last fenced JSON object from `text`, falling back to a raw parse.

    Returns (parsed_obj, error_message). Exactly one of the two is non-None.
    """
    matches = _JSON_FENCE_RE.findall(text)
    if matches:
        try:
            return json.loads(matches[-1]), None
        except json.JSONDecodeError as e:
            return None, f"last JSON fence failed to parse: {e}"
    # No fence — try parsing the trimmed text directly. Skills are supposed
    # to emit a fenced block, but be lenient.
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            return json.loads(stripped), None
        except json.JSONDecodeError as e:
            return None, f"trailing object failed to parse: {e}"
    return None, "no JSON object found in final assistant message"


def _collect_skills_invoked(transcript: list[str]) -> list[str]:
    """Walk every assistant turn, parse all JSON code blocks, and collect each
    distinct non-null `skill` value in first-seen order.

    Why scan the whole transcript and not just the final message: when Claude
    chains Skills (compound prompts), each Skill invocation ends with its own
    JSON output block in a separate assistant turn. The final message holds
    only the last Skill's report; earlier ones are recoverable only from the
    transcript.
    """
    seen: list[str] = []
    for turn in transcript:
        for raw in _JSON_FENCE_RE.findall(turn):
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            skill = obj.get("skill") if isinstance(obj, dict) else None
            if isinstance(skill, str) and skill and skill not in seen:
                seen.append(skill)
    return seen


async def run_agent(
    prompt: str,
    cwd: str,
    *,
    model: str = "claude-opus-4-7",
    allowed_tools: list[str] | None = None,
    max_turns: int = DEFAULT_MAX_TURNS,
    extra_env: dict[str, str] | None = None,
) -> AgentResult:
    """Run the agent in `cwd` and return the parsed final JSON block."""
    stderr_lines: list[str] = []

    def _capture_stderr(line: str) -> None:
        # Trim trailing newline; keep everything else as the CLI emits it so
        # multi-line tracebacks/JSON payloads stay intact when surfaced.
        stderr_lines.append(line.rstrip("\n"))

    options = ClaudeAgentOptions(
        model=model,
        cwd=cwd,
        # "project" loads <cwd>/.claude/{settings.json,skills/} — the Skills live there.
        setting_sources=["project"],
        allowed_tools=allowed_tools or DEFAULT_ALLOWED_TOOLS,
        # Non-interactive demo: never prompt for permission. Safety wall is
        # the repo allowlist + the scratch-dir cwd, not per-tool prompts.
        permission_mode="bypassPermissions",
        max_turns=max_turns,
        env=extra_env or {},
        # Capture stderr line-by-line so caller can see actual diagnostics
        # instead of the SDK's placeholder ProcessError text.
        stderr=_capture_stderr,
    )

    started = time.monotonic()
    last_assistant_text = ""
    transcript: list[str] = []
    num_turns: int | None = None
    cost_usd: float | None = None

    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                text = "".join(
                    block.text for block in message.content if isinstance(block, TextBlock)
                )
                if text:
                    last_assistant_text = text
                    transcript.append(text)
            elif isinstance(message, ResultMessage):
                num_turns = message.num_turns
                cost_usd = message.total_cost_usd
    except BaseException as e:
        # Re-raise but attach stderr so the caller's exception handler can
        # surface it. We use a custom attribute since the SDK's ProcessError
        # has a fixed shape.
        e.captured_stderr = stderr_lines  # type: ignore[attr-defined]
        raise

    parsed, err = _extract_last_json(last_assistant_text)
    return AgentResult(
        parsed=parsed,
        raw_final_text=last_assistant_text,
        duration_s=time.monotonic() - started,
        num_turns=num_turns,
        cost_usd=cost_usd,
        parse_error=err,
        transcript=transcript,
        stderr_lines=stderr_lines,
        skills_invoked=_collect_skills_invoked(transcript),
    )
