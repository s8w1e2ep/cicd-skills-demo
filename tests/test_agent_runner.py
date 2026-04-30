"""Unit tests for server.agent_runner.

The high-value target is `_extract_last_json` — every other piece in the file
is either a dataclass (no logic) or a thin wrapper around the SDK (better
covered by integration tests via run_eval.py against the live URL).

`_extract_last_json` is the contract between Claude's output and our API
response. If it silently breaks on a new shape Claude produces, every /run
returns parse_error and the demo looks broken even though the agent is fine.
That is the regression these tests are designed to catch.
"""

from server.agent_runner import _collect_skills_invoked, _extract_last_json


def test_extracts_single_fenced_json_block():
    text = """Some prose.

```json
{"skill": "lint-and-test", "status": "created"}
```
"""
    parsed, err = _extract_last_json(text)
    assert err is None
    assert parsed == {"skill": "lint-and-test", "status": "created"}


def test_takes_last_block_when_multiple_present():
    """If Claude emits intermediate JSON (e.g. tool inputs) followed by the
    final report, the last block is the authoritative one. Picking the first
    block silently returned tool inputs to the API client in an early version
    of this regex; that bug is what this test is for."""
    text = """
```json
{"intermediate": true}
```

Some text in between.

```json
{"skill": "lint-and-test", "status": "no_change"}
```
"""
    parsed, err = _extract_last_json(text)
    assert err is None
    assert parsed == {"skill": "lint-and-test", "status": "no_change"}


def test_handles_unfenced_trailing_json():
    """Fall back to parsing the trimmed text directly when no fence is present.
    Skills are *supposed* to use fences, but we don't want to fail the response
    on a missing fence if the JSON is otherwise unambiguous."""
    text = '{"skill": "lint-and-test", "status": "created"}'
    parsed, err = _extract_last_json(text)
    assert err is None
    assert parsed == {"skill": "lint-and-test", "status": "created"}


def test_handles_fence_without_json_language_tag():
    """Skills are instructed to use ```json but Claude sometimes uses bare
    ```. The regex allows the language tag to be optional so this still
    parses — failing on bare fences would surface as parse_error in 1 in N
    runs for no good reason."""
    text = """
```
{"skill": "security-scan", "status": "created"}
```
"""
    parsed, err = _extract_last_json(text)
    assert err is None
    assert parsed == {"skill": "security-scan", "status": "created"}


def test_returns_error_when_no_json_present():
    text = "No JSON here, just prose."
    parsed, err = _extract_last_json(text)
    assert parsed is None
    assert err is not None
    assert "no JSON object found" in err


def test_returns_error_when_fenced_json_is_malformed():
    """Properly fenced but malformed JSON (e.g. unquoted identifier where a
    string was expected) should surface as a parse error rather than being
    silently dropped. The regex requires balanced braces, so this case has
    a complete `{...}` body that json.loads then rejects."""
    text = """
```json
{"skill": "lint-and-test", "status": NOT_A_VALID_VALUE}
```
"""
    parsed, err = _extract_last_json(text)
    assert parsed is None
    assert err is not None
    assert "failed to parse" in err


def test_returns_error_when_json_is_truncated():
    """Different failure mode from `malformed`: when Claude's output is cut
    off mid-object, the regex never matches (no closing brace) and we fall
    through to the catch-all error. Both cases should surface a non-None err
    so the client knows the response is unusable — the exact message differs
    by failure shape."""
    text = """
```json
{"skill": "lint-and-test", "status": "creat
"""
    parsed, err = _extract_last_json(text)
    assert parsed is None
    assert err is not None  # message is implementation-detail; non-None is the contract


def test_ignores_prose_after_block():
    """SKILL.md tells Claude not to add prose after the JSON block, but if it
    does, the regex should still extract the block correctly. Trailing text
    is tolerated; we just take the last fenced block."""
    text = """
```json
{"skill": "lint-and-test", "status": "created"}
```

(I added the workflow.)
"""
    parsed, err = _extract_last_json(text)
    assert err is None
    assert parsed == {"skill": "lint-and-test", "status": "created"}


def test_collect_skills_invoked_picks_up_each_distinct_skill_in_order():
    """Compound prompts can chain Skills. The collector walks every assistant
    turn, parses each JSON code block, and records each non-null `skill` value
    once in invocation order — that's what the eval scorer checks against
    `ALL:` expectations."""
    transcript = [
        "Running lint-and-test now.\n```json\n"
        '{"skill": "lint-and-test", "status": "created"}\n```',
        "Now security-scan.\n```json\n"
        '{"skill": "security-scan", "status": "created"}\n```',
        "And dependency-audit.\n```json\n"
        '{"skill": "dependency-audit", "status": "no_change"}\n```',
    ]
    assert _collect_skills_invoked(transcript) == [
        "lint-and-test",
        "security-scan",
        "dependency-audit",
    ]


def test_collect_skills_invoked_dedupes_repeats():
    """If the same Skill emits more than one JSON block (rare but possible
    when Claude rerenders an output), it's still counted once."""
    transcript = [
        '```json\n{"skill": "lint-and-test", "status": "created"}\n```',
        '```json\n{"skill": "lint-and-test", "status": "no_change"}\n```',
    ]
    assert _collect_skills_invoked(transcript) == ["lint-and-test"]


def test_collect_skills_invoked_ignores_null_skill_blocks():
    """The NO_SKILL_FALLBACK_INSTRUCTION wrapper produces blocks with
    `skill: null` for refused / out-of-scope replies. Those don't count as
    Skill invocations."""
    transcript = [
        '```json\n{"skill": null, "status": "refused", "message": "no"}\n```',
    ]
    assert _collect_skills_invoked(transcript) == []


def test_collect_skills_invoked_skips_unparseable_blocks():
    """A malformed block in the middle of a transcript shouldn't take down
    the whole detection. Skip the bad one, keep going."""
    transcript = [
        '```json\n{"skill": "lint-and-test", "status": "created"}\n```',
        '```json\n{"skill": NOT_A_VALID_VALUE}\n```',
        '```json\n{"skill": "security-scan", "status": "created"}\n```',
    ]
    assert _collect_skills_invoked(transcript) == ["lint-and-test", "security-scan"]


def test_handles_nested_objects_in_json():
    """The status response has nested workflow_runs lists with objects inside
    — make sure the regex's lazy DOTALL match captures the whole structure."""
    text = """
```json
{
  "skill": "lint-and-test",
  "status": "created",
  "workflow_runs": [
    {"url": "https://github.com/foo/bar/actions/runs/1", "status": "queued", "conclusion": null}
  ],
  "refused": null
}
```
"""
    parsed, err = _extract_last_json(text)
    assert err is None
    assert parsed["skill"] == "lint-and-test"
    assert len(parsed["workflow_runs"]) == 1
    assert parsed["workflow_runs"][0]["status"] == "queued"
    assert parsed["refused"] is None
