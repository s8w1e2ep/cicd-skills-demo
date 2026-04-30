"""FastAPI demo service for the CI/CD Skills.

Endpoints:
  GET  /healthz                - liveness probe
  GET  /                       - single-page demo UI
  POST /run                    - free-form prompt; Claude picks a Skill
  POST /run/skill/{name}       - force a specific Skill (eval / debug)

The repo allowlist is the primary safety wall: the server hard-rejects any
target other than DEMO_REPO_URL, so even a jailbroken agent cannot touch
unrelated repos. The agent itself runs in a per-request scratch dir that is
deleted on the way out.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .agent_runner import run_agent

DEMO_REPO_URL = os.environ.get("DEMO_REPO_URL", "").rstrip("/")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
# Claude auth: either an Anthropic API key (Console billing, charged per call)
# or a long-lived OAuth token from `claude setup-token` (Pro/Max subscription
# billing). Per the auth precedence in
# https://code.claude.com/docs/en/authentication, ANTHROPIC_API_KEY is #3 and
# CLAUDE_CODE_OAUTH_TOKEN is #5 — so if both are set, the API key wins. Keep
# them mutually exclusive in deploy: Zeabur env vars should have one and only
# one of these.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_CODE_OAUTH_TOKEN = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")

DEMO_BRANCH = "claude/ci-demo"

# Identity used for commits the agent makes inside the scratch clone.
GIT_USER_NAME = os.environ.get("GIT_USER_NAME", "claude-skills-bot")
GIT_USER_EMAIL = os.environ.get("GIT_USER_EMAIL", "claude-skills-bot@users.noreply.github.com")

KNOWN_SKILLS = {
    "lint-and-test",
    "dependency-audit",
    "security-scan",
    "build-and-release",
}

# Prepended to free-form /run prompts so Claude returns JSON even when no
# Skill matches. Without this, out-of-scope or destructive requests come back
# as prose with output:null + parse_error — the agent does the right thing
# but the response shape is inconsistent. The contract carries Claude's full
# user-facing reply verbatim inside `message`, so nothing is lost in
# translation.
NO_SKILL_FALLBACK_INSTRUCTION = (
    "Output contract for this request:\n\n"
    "1. If the user's request enumerates multiple distinct CI/CD concerns "
    "that map to different Skills (for example: tests AND security scanning "
    "AND dependency auditing AND release automation), invoke each relevant "
    "Skill in turn. The Skills are independent and can run sequentially in "
    "the same session — each one will produce its own JSON output block at "
    "the end of its execution. Do not pick just one Skill and skip the "
    "others when the user has clearly asked for several.\n\n"
    "2. If your reply does not invoke any Skill — for example because the "
    "request is destructive (force-push, branch deletion, tag deletion), "
    "out-of-scope (anything outside `.github/workflows/`), or simply doesn't "
    "match any available Skill — your final assistant message must be a "
    "single JSON code block:\n\n"
    "```json\n"
    '{"skill": null, "status": "refused", '
    '"message": "<your full reply to the user, multi-line markdown allowed>"}\n'
    "```\n\n"
    "The `message` field is verbatim what the user will read — write it as "
    "you normally would (explanations, alternatives, clarifying questions). "
    "Do not add prose around the JSON block. When a Skill IS invoked, follow "
    "the Skill's own JSON contract — rule 2 does not apply.\n\n"
    "User request: "
)

app = FastAPI(title="cicd-skills-demo", version="0.1.0")

STATIC_DIR = Path(__file__).parent / "static"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    prompt: str
    repo_url: str | None = None  # optional; defaults to DEMO_REPO_URL


class RunResponse(BaseModel):
    output: dict[str, Any] | None
    raw_final_text: str
    duration_s: float
    num_turns: int | None = None
    cost_usd: float | None = None
    parse_error: str | None = None
    # Surface CLI stderr only when the run produced something — empty list
    # otherwise. Useful for spotting non-fatal warnings the SDK swallows.
    stderr_lines: list[str] = []
    # Names of every Skill that emitted a JSON output during the run, in
    # invocation order. For single-Skill prompts this matches `output.skill`;
    # for compound prompts that chained multiple Skills it lists all of them.
    skills_invoked: list[str] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_env() -> None:
    """Fail fast on missing config so we don't waste a Claude run.

    Claude auth is satisfied by either ANTHROPIC_API_KEY or
    CLAUDE_CODE_OAUTH_TOKEN — accept either one rather than requiring both.
    """
    missing = [
        name
        for name, val in [
            ("DEMO_REPO_URL", DEMO_REPO_URL),
            ("GITHUB_TOKEN", GITHUB_TOKEN),
        ]
        if not val
    ]
    if not (ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN):
        missing.append("ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN")
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"Service misconfigured: missing env var(s): {', '.join(missing)}",
        )


def _check_repo_allowlist(repo_url: str | None) -> None:
    target = (repo_url or DEMO_REPO_URL).rstrip("/")
    if target != DEMO_REPO_URL:
        raise HTTPException(
            status_code=400,
            detail=f"repo_url not in allowlist (expected {DEMO_REPO_URL})",
        )


def _authed_clone_url() -> str:
    """Embed the PAT in the clone URL so git push works without credential helpers.

    The token never appears in logs because we only pass it to subprocess as part of
    the URL argv, and git scrubs it from its own remote-tracking config on clone.
    """
    if DEMO_REPO_URL.startswith("https://github.com/"):
        return DEMO_REPO_URL.replace(
            "https://github.com/",
            f"https://x-access-token:{GITHUB_TOKEN}@github.com/",
        )
    return DEMO_REPO_URL  # SSH or other — caller's problem


def _prepare_scratch_clone() -> str:
    scratch = tempfile.mkdtemp(prefix="cicd-skills-")
    try:
        subprocess.run(
            ["git", "clone", "--depth", "20", _authed_clone_url(), scratch],
            check=True,
            capture_output=True,
            text=True,
        )
        # Best-effort: pre-fetch the demo branch so Skills can fast-forward on it.
        subprocess.run(
            ["git", "-C", scratch, "fetch", "origin", DEMO_BRANCH],
            capture_output=True,
            text=True,
        )
        # Configure committer identity for any commits the agent makes.
        subprocess.run(
            ["git", "-C", scratch, "config", "user.name", GIT_USER_NAME],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "-C", scratch, "config", "user.email", GIT_USER_EMAIL],
            check=True,
            capture_output=True,
            text=True,
        )
        return scratch
    except subprocess.CalledProcessError as e:
        shutil.rmtree(scratch, ignore_errors=True)
        # Don't leak the URL (which contains the PAT).
        raise HTTPException(
            status_code=502,
            detail=f"git clone failed: {e.stderr.strip().splitlines()[-1] if e.stderr else 'unknown error'}",
        ) from e


def _agent_env() -> dict[str, str]:
    """Env passed through to the agent's tool subprocesses (notably Bash → gh/git)."""
    return {
        # gh CLI uses GH_TOKEN preferentially; both are set for safety.
        "GH_TOKEN": GITHUB_TOKEN,
        "GITHUB_TOKEN": GITHUB_TOKEN,
        # Suppress gh's interactive prompts.
        "GH_PROMPT_DISABLED": "1",
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    """Liveness probe. Reports config presence and the runtime uid.

    The uid is reported because the bundled Claude Code CLI rejects
    --dangerously-skip-permissions when launched as root (uid 0). If the
    container ends up running as root despite the Dockerfile's `USER app`
    directive (e.g. platform overrides it), every /run will fail with a
    fast ProcessError; the uid here lets us confirm at a glance.
    """
    return {
        "ok": True,
        "demo_repo_configured": bool(DEMO_REPO_URL),
        "github_token_configured": bool(GITHUB_TOKEN),
        "anthropic_key_configured": bool(ANTHROPIC_API_KEY),
        "oauth_token_configured": bool(CLAUDE_CODE_OAUTH_TOKEN),
        "uid": os.getuid(),
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


def _agent_failure(e: BaseException) -> HTTPException:
    """Wrap any agent-side exception so the client sees the actual cause.

    Without this, an unhandled exception inside `run_agent()` returns FastAPI's
    generic 500 "Internal Server Error" body — opaque and forces a trip to
    server logs. We surface the type + message instead. Tracebacks stay in
    server logs (logged below); the client gets enough to decide what to do.

    If `run_agent` attached `captured_stderr` to the exception (the bundled
    CLI's stderr lines), include them in the response — that's where the real
    diagnostic content lives, since the SDK's ProcessError just bakes in a
    "Check stderr output for details" placeholder.
    """
    import logging
    import traceback

    logging.getLogger("uvicorn.error").error(
        "agent run failed: %s\n%s", e, traceback.format_exc()
    )
    detail: dict[str, Any] = {"error": e.__class__.__name__, "message": str(e)}
    captured = getattr(e, "captured_stderr", None)
    if captured:
        detail["stderr"] = captured
    return HTTPException(status_code=502, detail=detail)


@app.post("/run", response_model=RunResponse)
async def run_endpoint(req: RunRequest) -> RunResponse:
    """Free-form prompt — Claude picks the Skill."""
    _require_env()
    _check_repo_allowlist(req.repo_url)

    scratch = _prepare_scratch_clone()
    try:
        wrapped = NO_SKILL_FALLBACK_INSTRUCTION + req.prompt
        result = await run_agent(prompt=wrapped, cwd=scratch, extra_env=_agent_env())
        return RunResponse(
            output=result.parsed,
            raw_final_text=result.raw_final_text,
            duration_s=result.duration_s,
            num_turns=result.num_turns,
            cost_usd=result.cost_usd,
            parse_error=result.parse_error,
            stderr_lines=result.stderr_lines,
            skills_invoked=result.skills_invoked,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _agent_failure(e) from e
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


@app.get("/debug/cli-binary")
def debug_cli_binary() -> dict[str, Any]:
    """Locate the bundled Claude Code CLI and run it with --version.

    Goal: bypass the SDK's protocol layer entirely. If even `<cli> --version`
    exits 1 with no stderr, we know the CLI binary itself is broken (e.g.
    missing Node deps, bundled JS expects a runtime feature this Node lacks).
    If --version works but `<cli> -p "..."` doesn't, we know the protocol
    layer is the issue.
    """
    import subprocess
    import sys

    out: dict[str, Any] = {"python_executable": sys.executable}

    # Find the bundled CLI. claude_agent_sdk ships JS under its package dir.
    try:
        import claude_agent_sdk  # type: ignore

        sdk_dir = Path(claude_agent_sdk.__file__).parent
        out["sdk_dir"] = str(sdk_dir)
        # Walk the SDK dir looking for `cli.js` or similar entrypoints.
        candidates = []
        for path in sdk_dir.rglob("*"):
            if path.is_file() and path.name in {"cli.js", "claude.js", "index.js", "claude"}:
                candidates.append(str(path))
        out["cli_candidates"] = candidates[:20]
    except Exception as e:
        out["sdk_locate_error"] = repr(e)

    # Try to run `node --version` to confirm node itself works.
    try:
        node_v = subprocess.run(
            ["node", "--version"], capture_output=True, text=True, timeout=10
        )
        out["node_version"] = node_v.stdout.strip()
        out["node_stderr"] = node_v.stderr.strip()
    except Exception as e:
        out["node_run_error"] = repr(e)

    # Try the most likely CLI entrypoint paths. Bundled SDK candidates are
    # checked first because the previous probe showed no `claude` on PATH.
    candidate_paths = list(out.get("cli_candidates", [])) + [
        "/usr/local/bin/claude",
        "/usr/bin/claude",
        "/root/.npm-global/bin/claude",
    ]
    out["probes"] = []
    for candidate in candidate_paths:
        if not Path(candidate).exists():
            continue
        probe: dict[str, Any] = {"path": candidate}
        # Try invoking directly first (file may have a shebang or be executable).
        for argv in (
            [candidate, "--version"],
            ["node", candidate, "--version"],
        ):
            try:
                v = subprocess.run(
                    argv, capture_output=True, text=True, timeout=15,
                )
                probe[f"{argv[0]}__stdout"] = v.stdout
                probe[f"{argv[0]}__stderr"] = v.stderr
                probe[f"{argv[0]}__returncode"] = v.returncode
            except Exception as e:
                probe[f"{argv[0]}__error"] = repr(e)
        out["probes"].append(probe)

    return out


@app.post("/debug/cli-print")
def debug_cli_print() -> dict[str, Any]:
    """Invoke bundled CLI in one-shot print mode, fully bypassing the SDK.

    The previous probes confirmed:
      - CLI binary itself is healthy (--version returns 2.1.123)
      - In stream-json mode, the CLI signals errors via stdout protocol
        and leaves stderr empty (so we can't see the cause from there)

    By invoking `claude -p "<prompt>"`, the CLI runs in print mode rather
    than as a stream server. Print-mode errors land on stderr where we
    can capture them with subprocess.run, finally giving us a real
    error message.
    """
    import subprocess

    _require_env()
    cli_path = "/usr/local/lib/python3.12/site-packages/claude_agent_sdk/_bundled/claude"
    out: dict[str, Any] = {"cli_path": cli_path}
    if not Path(cli_path).exists():
        out["error"] = "bundled CLI not at expected path"
        return out

    env = {
        **os.environ,
        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
        "IS_SANDBOX": "1",
    }
    try:
        v = subprocess.run(
            [cli_path, "-p", "Reply with exactly the word ok and nothing else."],
            capture_output=True, text=True, timeout=60, env=env,
        )
        out["returncode"] = v.returncode
        out["stdout"] = v.stdout
        out["stderr"] = v.stderr
    except subprocess.TimeoutExpired as e:
        out["error"] = "timeout"
        out["partial_stdout"] = (e.stdout or b"").decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        out["partial_stderr"] = (e.stderr or b"").decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
    except Exception as e:
        out["error"] = repr(e)
    return out


@app.post("/debug/cli-probe")
async def debug_cli_probe() -> dict[str, Any]:
    """Smallest possible agent invocation, with full stderr capture.

    Bypasses Skill loading and tool use — just asks Claude to reply with one
    word. If this fails, the issue is in CLI startup / API auth / network
    egress, not in our Skill setup. The response always returns 200 so the
    client can read the diagnostics regardless of whether the agent worked.
    """
    _require_env()
    from .agent_runner import run_agent  # local import keeps this isolated

    out: dict[str, Any] = {
        "demo_repo_url": DEMO_REPO_URL,
        "uid": os.getuid(),
        "anthropic_key_present": bool(ANTHROPIC_API_KEY),
        "anthropic_key_length": len(ANTHROPIC_API_KEY),
        "github_token_present": bool(GITHUB_TOKEN),
    }
    # Use a temp dir, not the demo clone — we want to test CLI bringup in
    # isolation from any Skill / git logic.
    scratch = tempfile.mkdtemp(prefix="cli-probe-")
    try:
        result = await run_agent(
            prompt="Reply with exactly the word 'ok' and nothing else.",
            cwd=scratch,
            allowed_tools=[],
            max_turns=1,
            extra_env=_agent_env(),
        )
        out["status"] = "ok"
        out["raw_final_text"] = result.raw_final_text
        out["duration_s"] = result.duration_s
        out["stderr_lines"] = result.stderr_lines
    except Exception as e:
        import traceback

        out["status"] = "error"
        out["error_type"] = e.__class__.__name__
        out["error_message"] = str(e)
        out["stderr_lines"] = getattr(e, "captured_stderr", []) or []
        out["traceback"] = traceback.format_exc().splitlines()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return out


@app.post("/run/skill/{name}", response_model=RunResponse)
async def run_skill_endpoint(name: str, req: RunRequest) -> RunResponse:
    """Force a specific Skill — used by the eval harness and debugging."""
    _require_env()
    _check_repo_allowlist(req.repo_url)
    if name not in KNOWN_SKILLS:
        raise HTTPException(
            status_code=404,
            detail=f"unknown skill: {name}. known: {sorted(KNOWN_SKILLS)}",
        )

    # Wrap the user prompt so Claude is unambiguous about which Skill to use.
    forced_prompt = (
        f"Use the `{name}` skill to handle this request. "
        f"Do not invoke any other skill. "
        f"User request: {req.prompt}"
    )

    scratch = _prepare_scratch_clone()
    try:
        result = await run_agent(prompt=forced_prompt, cwd=scratch, extra_env=_agent_env())
        return RunResponse(
            output=result.parsed,
            raw_final_text=result.raw_final_text,
            duration_s=result.duration_s,
            num_turns=result.num_turns,
            cost_usd=result.cost_usd,
            parse_error=result.parse_error,
            stderr_lines=result.stderr_lines,
            skills_invoked=result.skills_invoked,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _agent_failure(e) from e
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
