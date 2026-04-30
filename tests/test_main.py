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
    monkeypatch.setattr(server.main, "CLAUDE_CODE_OAUTH_TOKEN", "")
    return server.main


@pytest.fixture
def configured_oauth(monkeypatch):
    """Same as `configured` but uses an OAuth token instead of API key.

    Mirrors the deploy mode where Pro/Max subscription auth replaces API
    billing — we want to confirm /run still works in this configuration.
    """
    import server.main

    monkeypatch.setattr(server.main, "DEMO_REPO_URL", "https://github.com/test/demo")
    monkeypatch.setattr(server.main, "GITHUB_TOKEN", "ghp_test_token")
    monkeypatch.setattr(server.main, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(server.main, "CLAUDE_CODE_OAUTH_TOKEN", "oauth-test-token")
    return server.main


@pytest.fixture
def unconfigured(monkeypatch):
    import server.main

    monkeypatch.setattr(server.main, "DEMO_REPO_URL", "")
    monkeypatch.setattr(server.main, "GITHUB_TOKEN", "")
    monkeypatch.setattr(server.main, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(server.main, "CLAUDE_CODE_OAUTH_TOKEN", "")
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
    assert body["oauth_token_configured"] is False
    assert isinstance(body["uid"], int)


def test_healthz_reports_oauth_configured(configured_oauth):
    """Pro/Max subscription deploy: OAuth token, no API key."""
    client = TestClient(configured_oauth.app)
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["anthropic_key_configured"] is False
    assert body["oauth_token_configured"] is True


def test_healthz_reports_unconfigured(unconfigured):
    client = TestClient(unconfigured.app)
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["demo_repo_configured"] is False
    assert body["github_token_configured"] is False
    assert body["anthropic_key_configured"] is False
    assert body["oauth_token_configured"] is False


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
    assert "ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN" in detail


def test_run_accepts_oauth_only_config(configured_oauth, monkeypatch):
    """OAuth-only deploy is a valid config — /run should pass _require_env."""
    monkeypatch.setattr(configured_oauth, "_prepare_scratch_clone", lambda: "/tmp/fake")
    monkeypatch.setattr("shutil.rmtree", lambda *a, **kw: None)

    async def fake_run_agent(**kwargs):
        from server.agent_runner import AgentResult

        return AgentResult(
            parsed={"skill": "lint-and-test", "status": "created"},
            raw_final_text="",
            duration_s=0.1,
            num_turns=1,
            cost_usd=None,
        )

    monkeypatch.setattr(configured_oauth, "run_agent", fake_run_agent)
    client = TestClient(configured_oauth.app)
    r = client.post("/run", json={"prompt": "test"})
    assert r.status_code == 200


def test_run_prepends_no_skill_fallback_instruction(configured, monkeypatch):
    """The free-form /run endpoint must wrap the user prompt with the
    fallback instruction so Claude returns JSON even on out-of-scope
    requests. /run/skill/{name} must NOT add this wrapper — the forced
    Skill already has its own JSON contract.
    """
    monkeypatch.setattr(configured, "_prepare_scratch_clone", lambda: "/tmp/fake")
    monkeypatch.setattr("shutil.rmtree", lambda *a, **kw: None)
    captured = {}

    async def fake_run_agent(**kwargs):
        captured.update(kwargs)
        from server.agent_runner import AgentResult

        return AgentResult(
            parsed={"skill": None, "status": "refused", "message": "no"},
            raw_final_text="",
            duration_s=0.1,
            num_turns=1,
            cost_usd=None,
        )

    monkeypatch.setattr(configured, "run_agent", fake_run_agent)
    client = TestClient(configured.app)
    r = client.post("/run", json={"prompt": "delete production database"})
    assert r.status_code == 200
    assert configured.NO_SKILL_FALLBACK_INSTRUCTION in captured["prompt"]
    assert "delete production database" in captured["prompt"]
    # The instruction must precede the user prompt so Claude reads the
    # contract before the request itself.
    assert captured["prompt"].endswith("delete production database")


def test_run_skill_does_not_prepend_fallback_instruction(configured, monkeypatch):
    """Forced-skill route bypasses the fallback wrapper — the Skill always
    triggers, so the free-form fallback contract would just be noise."""
    monkeypatch.setattr(configured, "_prepare_scratch_clone", lambda: "/tmp/fake")
    monkeypatch.setattr("shutil.rmtree", lambda *a, **kw: None)
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

    monkeypatch.setattr(configured, "run_agent", fake_run_agent)
    client = TestClient(configured.app)
    r = client.post("/run/skill/lint-and-test", json={"prompt": "ci please"})
    assert r.status_code == 200
    assert configured.NO_SKILL_FALLBACK_INSTRUCTION not in captured["prompt"]
    assert "Use the `lint-and-test` skill" in captured["prompt"]


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


def test_pipeline_accepts_empty_body(unconfigured):
    """The pipeline endpoint builds its own prompts internally — clients
    should be able to POST {} without a prompt field. With env unset we
    expect 503 (env validation runs before any body-derived logic)."""
    client = TestClient(unconfigured.app)
    r = client.post("/run/cicd-pipeline", json={})
    assert r.status_code == 503
    assert "missing env var" in r.json()["detail"]


def test_pipeline_rejects_non_allowlisted_repo_url(configured):
    """Repo allowlist applies to the pipeline endpoint as well — the safety
    wall must wrap every entry point that ends up cloning."""
    client = TestClient(configured.app)
    r = client.post(
        "/run/cicd-pipeline",
        json={"repo_url": "https://github.com/elsewhere/repo"},
    )
    assert r.status_code == 400
    assert "allowlist" in r.json()["detail"]


def test_generate_pipeline_branch_format(configured):
    """Branch names embed UTC timestamp + 6 hex chars so two clicks within
    the same second don't collide."""
    import re

    name = configured._generate_pipeline_branch()
    assert re.fullmatch(r"demo-\d{8}-\d{6}-[0-9a-f]{6}", name), name


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


# ---------------------------------------------------------------------------
# Tag-bump pure helpers
# ---------------------------------------------------------------------------


def test_pick_next_release_tag_empty_input(configured):
    """No tags yet → start at v0.1.0. The first pipeline run on a brand-new
    repo must still produce a pushable tag."""
    assert configured._pick_next_release_tag([]) == "v0.1.0"


def test_pick_next_release_tag_handles_non_list(configured):
    """gh sometimes returns an error object instead of an array (e.g. when
    the repo has no /git/refs/tags resource yet on a fresh repo). Anything
    that isn't a list falls back to v0.1.0 rather than raising."""
    assert configured._pick_next_release_tag(None) == "v0.1.0"
    assert configured._pick_next_release_tag({"message": "Not Found"}) == "v0.1.0"
    assert configured._pick_next_release_tag("not json") == "v0.1.0"


def test_pick_next_release_tag_picks_max_and_bumps_patch(configured):
    """Highest semver wins, patch increments. Order in the list must not
    matter — we don't trust gh to sort."""
    refs = [
        {"ref": "refs/tags/v0.1.0"},
        {"ref": "refs/tags/v0.2.5"},
        {"ref": "refs/tags/v0.1.7"},
    ]
    assert configured._pick_next_release_tag(refs) == "v0.2.6"


def test_pick_next_release_tag_ignores_non_semver_tags(configured):
    """Tags like `latest`, `release-2026Q2`, `v1` (two-part) shouldn't
    confuse the picker — only `vMAJOR.MINOR.PATCH` counts."""
    refs = [
        {"ref": "refs/tags/latest"},
        {"ref": "refs/tags/release-2026Q2"},
        {"ref": "refs/tags/v1"},
        {"ref": "refs/tags/v0.1.0-rc1"},
        {"ref": "refs/tags/v0.1.3"},
    ]
    assert configured._pick_next_release_tag(refs) == "v0.1.4"


def test_pick_next_release_tag_only_non_semver_falls_back(configured):
    """Repo has tags but none are semver-shaped — same fallback as empty."""
    refs = [
        {"ref": "refs/tags/latest"},
        {"ref": "refs/tags/v1"},  # missing minor + patch
    ]
    assert configured._pick_next_release_tag(refs) == "v0.1.0"


def test_pick_next_release_tag_skips_malformed_entries(configured):
    """A None or non-dict inside the list shouldn't take down the picker —
    skip it and keep going."""
    refs = [
        None,
        "garbage",
        {"ref": "refs/tags/v0.5.0"},
        42,
    ]
    assert configured._pick_next_release_tag(refs) == "v0.5.1"


def test_pick_next_release_tag_handles_major_minor_rollover(configured):
    """No special-casing — patch always increments, even when MINOR is huge."""
    refs = [{"ref": "refs/tags/v2.99.99"}]
    assert configured._pick_next_release_tag(refs) == "v2.99.100"


def test_owner_repo_parses_https_url(configured, monkeypatch):
    """The standard demo URL form."""
    monkeypatch.setattr(configured, "DEMO_REPO_URL", "https://github.com/octo/demo")
    assert configured._owner_repo() == ("octo", "demo")


def test_owner_repo_strips_dot_git_and_trailing_slash(configured, monkeypatch):
    """Both common variants of the same URL."""
    for url in (
        "https://github.com/octo/demo.git",
        "https://github.com/octo/demo/",
        "https://github.com/octo/demo.git/",
    ):
        monkeypatch.setattr(configured, "DEMO_REPO_URL", url)
        assert configured._owner_repo() == ("octo", "demo"), f"failed for {url}"


def test_owner_repo_returns_none_for_non_github(configured, monkeypatch):
    """SSH form, GitLab, or anything that's not a github.com https URL.
    The pipeline should treat the tag-bump as unsupported rather than
    crash on a regex miss."""
    for url in (
        "git@github.com:octo/demo",
        "https://gitlab.com/octo/demo",
        "https://example.com/repo",
        "",
    ):
        monkeypatch.setattr(configured, "DEMO_REPO_URL", url)
        assert configured._owner_repo() is None, f"should reject {url!r}"


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
