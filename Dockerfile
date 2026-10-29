FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git curl \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

ENV PORT=8790 GM_DATA_DIR=/app/data GM_WORKTREES_DIR=/app/wt
EXPOSE 8790

# ACCESS_CODE must be supplied at run time; the server refuses to start
# without it. gh auth must be provided (e.g. GH_TOKEN) for scan/push.
CMD ["python3", "server.py"]
