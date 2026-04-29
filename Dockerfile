# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Runtime deps:
# - git, gh CLI: used by the Skills' Bash steps to push branches and open PRs
# - Node.js (NodeSource 20.x): claude-agent-sdk's "bundled" CLI is JS that spawns
#   under `node`. Without a Node runtime, query.initialize() exits 1 immediately
#   and every /run call returns 502 with no usable stderr surfaced. Earlier
#   commit messages (and an earlier comment here) said "no Node needed because
#   bundled" — that was wrong; bundled means the JS payload, not the runtime.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        git \
        ca-certificates \
        curl \
        gnupg \
 && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | gpg --dearmor -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
 && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends gh nodejs \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY pyproject.toml ./
COPY .claude ./.claude
COPY server ./server
COPY README.md* CLAUDE.md spec.md plan.md task.md ./

# The bundled Claude Code CLI refuses to run with --dangerously-skip-permissions
# under root ("cannot be used with root/sudo privileges for security reasons"),
# which is what permission_mode="bypassPermissions" maps to. Containers default
# to root, so we create an unprivileged user and switch to it. /app needs to be
# owned by that user so per-request scratch dirs (created via tempfile under
# /tmp by default, but file-writes during clone happen in /app's git config etc.)
# don't hit EACCES.
RUN useradd --create-home --shell /bin/bash app \
 && chown -R app:app /app
USER app

# Honour $PORT if the platform injects one (Zeabur, Heroku-style); fall back to 8000.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn server.main:app --host 0.0.0.0 --port ${PORT}"]
