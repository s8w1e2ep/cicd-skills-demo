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
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_env() -> None:
    """Fail fast on missing config so we don't waste a Claude run."""
    missing = [
        name
        for name, val in [
            ("DEMO_REPO_URL", DEMO_REPO_URL),
            ("GITHUB_TOKEN", GITHUB_TOKEN),
            ("ANTHROPIC_API_KEY", ANTHROPIC_API_KEY),
        ]
        if not val
    ]
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
        result = await run_agent(prompt=req.prompt, cwd=scratch, extra_env=_agent_env())
        return RunResponse(
            output=result.parsed,
            raw_final_text=result.raw_final_text,
            duration_s=result.duration_s,
            num_turns=result.num_turns,
            cost_usd=result.cost_usd,
            parse_error=result.parse_error,
            stderr_lines=result.stderr_lines,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _agent_failure(e) from e
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


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
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _agent_failure(e) from e
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
