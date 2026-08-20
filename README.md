# Peearh

A FastAPI bot that reviews GitHub pull requests with an OpenAI-compatible LLM. The default setup is [OpenRouter](https://openrouter.ai/) (`qwen/qwen3-coder`, the 480B-A35B-Instruct model). Any other OpenAI-compatible endpoint (including local [LM Studio](https://lmstudio.ai/)) works by changing `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL`.

GitHub sends a webhook when a PR is opened, marked ready, or updated with new commits. Peearh verifies the signature, hands the diff to the **agent registered for that repository**, and posts a GitHub review: a summary plus inline comments on real diff lines.

One agent per repo. Each agent stores a short brief (what the project is, what to focus on) and uses it in the review prompt.

## How it works

```
GitHub --HTTPS--> ngrok / Cloudflare Tunnel --> FastAPI (host :8008)
                                                    |
                                                    +--> GitHub REST (diff + review)
                                                    +--> OpenRouter (or any OpenAI-compatible /v1)
```

The tunnel only exposes FastAPI. The LLM is whatever `LLM_BASE_URL` in `.env` points at.

Triggers: `pull_request` actions `opened`, `ready_for_review`, and `synchronize`. Drafts are skipped. The same head SHA is not reviewed twice. Reviews are posted as `COMMENT` (never approve / request changes).

## Setup

### 1. Config files

```bash
cp .env.example .env
cp repos.example.yaml repos.yaml
```

Edit `.env`:

- `GITHUB_TOKEN` — personal access token (below)
- `GITHUB_WEBHOOK_SECRET` — long random string, same value you will put on the GitHub webhook
- `LLM_BASE_URL` — `https://openrouter.ai/api/v1` (must include `/api/v1`)
- `LLM_API_KEY` — OpenRouter key (`sk-or-v1-...`)
- `LLM_MODEL` — `qwen/qwen3-coder` (OpenRouter’s id for Qwen3-Coder-480B-A35B-Instruct)

Edit `repos.yaml` and register each repo you want reviewed (one agent per entry).

### 2. GitHub personal access token

Fine-grained PAT, one or more repos you own:

- **Contents**: Read
- **Pull requests**: Read and write
- **Metadata**: Read

Classic token fallback: `repo`.

### 3. LLM (OpenRouter)

Create a key at [openrouter.ai](https://openrouter.ai/). The app uses the OpenAI-compatible Chat Completions API:

```
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=sk-or-v1-...
LLM_MODEL=qwen/qwen3-coder
```

To use local LM Studio instead, set `LLM_BASE_URL=http://127.0.0.1:1234/v1` (from Docker: `http://host.docker.internal:1234/v1`), `LLM_API_KEY=lm-studio`, and start the LM Studio server on `0.0.0.0:1234`.

### 4. Run with Docker (preferred)

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Engine + Compose).

```bash
docker compose up --build
```

The API is [http://127.0.0.1:8008](http://127.0.0.1:8008).

| Piece | Role |
| --- | --- |
| `Dockerfile` | Python 3.12 slim, installs the package, serves with uvicorn on `0.0.0.0:8000` |
| `docker-compose.yml` | `app` on host port **8008** (container still listens on 8000); mounts `./repos.yaml`; loads `.env` |
| `.dockerignore` | Keeps `.venv`, `.git`, tests, and `.env` out of the image |

Compose sets `REPOS_FILE=/app/repos.yaml` (your `./repos.yaml`). `LLM_BASE_URL` and the API key come from `.env` unchanged, so OpenRouter works inside the container.

```bash
docker compose logs -f        # follow the API
docker compose down           # stop
docker compose up -d --build  # rebuild and run in the background
```

**Port 8008 already in use?** Stop whatever is bound to it, or change the left-hand side of `8008:8000` in `docker-compose.yml`.

**`/health/llm` failing?** Confirm `.env` uses `https://openrouter.ai/api/v1` (not the site root) and that Compose is not overriding `LLM_BASE_URL`. Then:

```bash
curl -sS http://127.0.0.1:8008/health/llm
```

Register another repo against the running container:

```bash
curl -X POST http://127.0.0.1:8008/repos \
  -H 'Content-Type: application/json' \
  -d '{"repo":"your-org/web","name":"Web","description":"Storefront","review_focus":"XSS"}'
```

That write goes to the mounted `repos.yaml`, so it survives `docker compose down`.

### 5. Run without Docker

Python 3.11+ (macOS system `python3` is often 3.9; use Homebrew `python3.13` if needed).

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# .env and repos.yaml — same as step 1
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The venv process reads the same `.env` (OpenRouter by default).

### 6. Tunnel and GitHub webhook

Keep ngrok (or cloudflared) on the **host**. With Docker it must target the published port:

```bash
ngrok http 8008
# or
cloudflared tunnel --url http://127.0.0.1:8008
```

Without Docker, point the tunnel at `8000` instead (the venv `uvicorn` port).

On **each** registered repo (or one org hook):

- Payload URL: `https://<tunnel-host>/webhooks/github`
- Content type: `application/json`
- Secret: same as `GITHUB_WEBHOOK_SECRET`
- Events: **Pull requests** only

A quick tunnel URL changes every restart. Update the webhook, or use a named Cloudflare tunnel.

`GET /health` should be `{"status":"ok"}`. `GET /health/llm` lists models from the configured provider.

Unknown repos are ignored unless `ALLOW_UNREGISTERED=true` (then Peearh fetches the GitHub description and creates an agent on first webhook).

## What a review looks like

The agent for that repo posts one review on the head SHA:

- Markdown summary (agent name, per-file notes, skipped files)
- Inline comments only on lines that exist in the PR diff
- Notes the model attached to a non-diff line go under **Could not attach**
- On a hard failure (LLM unreachable, GitHub 5xx), a short issue comment is posted so it is not silent

## HTTP API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Process is up |
| GET | `/health/llm` | Configured LLM reachable |
| GET | `/repos` | Registered agents |
| GET | `/repos/{owner}/{name}` | One agent brief |
| POST | `/repos` | Register / update an agent |
| GET | `/jobs/{id}` | Webhook job status |
| POST | `/webhooks/github` | GitHub webhook |

## Tests

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

No live GitHub or LLM required. Tests run on the host, not in the image.

## Config

| Env | Default | Meaning |
| --- | --- | --- |
| `GITHUB_WEBHOOK_SECRET` | required | HMAC secret |
| `GITHUB_TOKEN` | required | PAT |
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1` | OpenAI-compatible base URL |
| `LLM_API_KEY` | required | OpenRouter (or other provider) API key |
| `LLM_MODEL` | `qwen/qwen3-coder` | OpenRouter id for Qwen3-Coder-480B-A35B-Instruct. Empty = first model from `GET /v1/models` |
| `LLM_MAX_TOKENS` | `4096` | Max completion tokens. Required on OpenRouter so the request is not billed as 65k |
| `MAX_FILES` | `30` | Files reviewed per PR |
| `MAX_PATCH_CHARS` | `20000` | Skip larger file patches |
| `LLM_TIMEOUT_SECONDS` | `180` | Per completion |
| `REPOS_FILE` | `repos.yaml` | Agent registry. Compose sets `/app/repos.yaml` |
| `ALLOW_UNREGISTERED` | `false` | Auto-create agents on first webhook |

Jobs are in-memory. A container or process restart drops in-flight reviews. Registered repo briefs persist in `repos.yaml`.
