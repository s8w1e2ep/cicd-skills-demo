"""Unit tests for server.main.

Endpoint-level tests use FastAPI's TestClient. We patch module-level config
and `run_agent` because we don't want pytest to actually invoke the Claude
SDK (slow, costs money, requires API key).

The `_authed_clone_url` function is tested in isolation since it has logic
worth verifying (PAT injection, https vs ssh handling) and is called inside
`_prepare_scratch_clone` which we don't directly test.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def configured(monkeypatch):
    """Patch module-level env-var constants to a configured state.

    server.main reads env vars at import time, so monkeypatch.setenv after
    import has no effect — we patch the module attributes directly.
    """
    import server.main

    monkeypatch.setattr(server.main, "DEMO_REPO_URL", "https://github.com/test/demo")
    monkeypatch.setattr(server.main, "GITHUB_TOKEN", "ghp_test_token")
    monkeypatch.setattr(server.main, "ANTHROPIC_API_KEY", "sk-ant-test")
    return server.main


@pytest.fixture
def unconfigured(monkeypatch):
    import server.main

    monkeypatch.setattr(server.main, "DEMO_REPO_URL", "")
    monkeypatch.setattr(server.main, "GITHUB_TOKEN", "")
    monkeypatch.setattr(server.main, "ANTHROPIC_API_KEY", "")
    return server.main


# ---------------------------------------------------------------------------
# /healthz
# ---------------------------------------------------------------------------


def test_healthz_reports_all_configured(configured):
    client = TestClient(configured.app)
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["demo_repo_configured"] is True
    assert body["github_token_configured"] is True
    assert body["anthropic_key_configured"] is True
    assert isinstance(body["uid"], int)


def test_healthz_reports_unconfigured(unconfigured):
    client = TestClient(unconfigured.app)
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["demo_repo_configured"] is False
    assert body["github_token_configured"] is False
    assert body["anthropic_key_configured"] is False


# ---------------------------------------------------------------------------
# /run — the safety wall
# ---------------------------------------------------------------------------


def test_run_returns_503_when_not_configured(unconfigured):
    """Server fails fast if any required env var is missing — saves a Claude
    SDK invocation that would just blow up on the first git clone."""
    client = TestClient(unconfigured.app)
    r = client.post("/run", json={"prompt": "test"})
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert "missing env var" in detail
    assert "DEMO_REPO_URL" in detail


def test_run_rejects_non_allowlisted_repo_url(configured):
    """The repo allowlist is the primary safety wall: even a jailbroken agent
    cannot touch repos other than DEMO_REPO_URL because the orchestrator
    refuses to clone them."""
    client = TestClient(configured.app)
    r = client.post(
        "/run",
        json={"prompt": "test", "repo_url": "https://github.com/elsewhere/repo"},
    )
    assert r.status_code == 400
    assert "allowlist" in r.json()["detail"]


def test_run_accepts_explicit_matching_repo_url(configured, monkeypatch):
    """Passing the configured DEMO_REPO_URL explicitly should not be rejected.
    We mock _prepare_scratch_clone to avoid actually shelling out to git."""
    monkeypatch.setattr(configured, "_prepare_scratch_clone", lambda: "/tmp/fake")
    monkeypatch.setattr("shutil.rmtree", lambda *a, **kw: None)

    async def fake_run_agent(**kwargs):
        from server.agent_runner import AgentResult

        return AgentResult(
            parsed={"skill": "lint-and-test", "status": "created"},
            raw_final_text='{"skill": "lint-and-test", "status": "created"}',
            duration_s=0.1,
            num_turns=1,
            cost_usd=None,
        )

    monkeypatch.setattr(configured, "run_agent", fake_run_agent)

    client = TestClient(configured.app)
    r = client.post(
        "/run",
        json={
            "prompt": "set up CI",
            "repo_url": "https://github.com/test/demo",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["output"]["skill"] == "lint-and-test"


def test_run_with_trailing_slash_in_repo_url_still_accepts(configured, monkeypatch):
    """Users (and the eval harness) sometimes pass URLs with a trailing slash.
    The allowlist check normalises both sides via .rstrip('/')."""
    monkeypatch.setattr(configured, "_prepare_scratch_clone", lambda: "/tmp/fake")
    monkeypatch.setattr("shutil.rmtree", lambda *a, **kw: None)

    async def fake_run_agent(**kwargs):
        from server.agent_runner import AgentResult

        return AgentResult(
            parsed={"skill": "lint-and-test", "status": "no_change"},
            raw_final_text="",
            duration_s=0.1,
            num_turns=1,
            cost_usd=None,
        )

    monkeypatch.setattr(configured, "run_agent", fake_run_agent)
    client = TestClient(configured.app)
    r = client.post(
        "/run",
        json={
            "prompt": "test",
            "repo_url": "https://github.com/test/demo/",  # trailing slash
        },
    )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# /run/skill/{name}
# ---------------------------------------------------------------------------


def test_run_skill_unknown_name_returns_404(configured):
    client = TestClient(configured.app)
    r = client.post("/run/skill/not-a-real-skill", json={"prompt": "test"})
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert "unknown skill" in detail
    assert "not-a-real-skill" in detail


def test_run_skill_known_name_passes_through(configured, monkeypatch):
    """Forced-skill endpoint should wrap the prompt with the skill name and
    invoke run_agent. We assert on the wrapped prompt to confirm the
    'Use the X skill' framing actually reaches the agent."""
    captured = {}

    async def fake_run_agent(**kwargs):
        captured.update(kwargs)
        from server.agent_runner import AgentResult

        return AgentResult(
            parsed={"skill": "lint-and-test", "status": "created"},
            raw_final_text="",
            duration_s=0.1,
            num_turns=1,
            cost_usd=None,
        )

    monkeypatch.setattr(configured, "_prepare_scratch_clone", lambda: "/tmp/fake")
    monkeypatch.setattr(configured, "run_agent", fake_run_agent)
    monkeypatch.setattr("shutil.rmtree", lambda *a, **kw: None)

    client = TestClient(configured.app)
    r = client.post("/run/skill/lint-and-test", json={"prompt": "do thing"})
    assert r.status_code == 200
    assert "Use the `lint-and-test` skill" in captured["prompt"]
    assert "User request: do thing" in captured["prompt"]


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_authed_clone_url_inserts_pat(configured):
    """The clone URL must embed the token via x-access-token so git push
    works without configuring a credential helper inside the container."""
    url = configured._authed_clone_url()
    assert "x-access-token:ghp_test_token@github.com" in url
    assert url.endswith("/test/demo")


def test_authed_clone_url_passthrough_for_non_https(configured, monkeypatch):
    """SSH URLs are returned unchanged — token injection only makes sense for
    https. (We don't actually use SSH in production, but the function should
    not corrupt other URL shapes if env is misconfigured.)"""
    monkeypatch.setattr(configured, "DEMO_REPO_URL", "git@github.com:test/demo")
    url = configured._authed_clone_url()
    assert url == "git@github.com:test/demo"
