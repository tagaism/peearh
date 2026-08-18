# Peearh

A local FastAPI bot that reviews GitHub pull requests with the model loaded in [LM Studio](https://lmstudio.ai/).

GitHub sends a webhook when a PR is opened (or a draft is marked ready). Peearh verifies the signature, hands the diff to the **agent registered for that repository**, and posts a GitHub review: a summary plus inline comments on real diff lines.

One agent per repo. Each agent stores a short brief (what the project is, what to focus on) and uses it in the review prompt.

## How it works

```
GitHub --HTTPS--> Cloudflare Tunnel / ngrok --> FastAPI :8000
                                                    |
                                                    +--> GitHub REST (diff + review)
                                                    +--> LM Studio http://127.0.0.1:1234/v1
```

The tunnel only exposes FastAPI. LM Studio stays on localhost.

Triggers: `pull_request` actions `opened` and `ready_for_review`. Drafts are skipped. Reviews are posted as `COMMENT` (never approve / request changes).

## Setup

### 1. Install

Python 3.11+ (macOS system `python3` is often 3.9; use Homebrew `python3.13` if needed).

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
cp repos.example.yaml repos.yaml
```

### 2. GitHub personal access token

Fine-grained PAT, one or more repos you own:

- **Contents**: Read
- **Pull requests**: Read and write
- **Metadata**: Read

Classic token fallback: `repo`.

Put it in `.env` as `GITHUB_TOKEN`. Also set `GITHUB_WEBHOOK_SECRET` to a long random string.

### 3. Register repositories (one agent each)

Edit `repos.yaml`:

```yaml
repos:
  - repo: your-org/api
    name: API
    description: Order-taking HTTP API. Payments live in a sibling service.
    review_focus: authz, input validation, and backwards-compatible contracts

  - repo: your-org/web
    name: Web
    description: Customer storefront.
    review_focus: XSS, broken UI state, and accessibility
```

You can also add one at runtime:

```bash
curl -X POST http://127.0.0.1:8000/repos \
  -H 'Content-Type: application/json' \
  -d '{"repo":"your-org/web","name":"Web","description":"Storefront","review_focus":"XSS"}'
```

Unknown repos are ignored unless `ALLOW_UNREGISTERED=true` (then Peearh fetches the GitHub description and creates an agent on first webhook).

### 4. LM Studio

1. Load a model.
2. Start the local server (default `http://127.0.0.1:1234`).
3. Leave `LLM_MODEL` empty to use the first loaded model, or set it to the model id.

### 5. Run the app and a tunnel

```bash
# terminal 1
uvicorn app.main:app --host 127.0.0.1 --port 8000

# terminal 2 — pick one
cloudflared tunnel --url http://127.0.0.1:8000
# or
ngrok http 8000
```

A quick tunnel URL changes every restart. Update the webhook, or use a named Cloudflare tunnel.

### 6. Create the GitHub webhook

On **each** repo (or on the org, if you prefer one hook):

- Payload URL: `https://<tunnel-host>/webhooks/github`
- Content type: `application/json`
- Secret: same as `GITHUB_WEBHOOK_SECRET`
- Events: **Pull requests** only

`GET /health` should be `{"status":"ok"}`. `GET /health/llm` lists models from LM Studio.

## What a review looks like

The agent for that repo posts one review on the head SHA:

- Markdown summary (agent name, per-file notes, skipped files)
- Inline comments only on lines that exist in the PR diff
- Notes the model attached to a non-diff line go under **Could not attach**
- On a hard failure (LM Studio down, GitHub 5xx), a short issue comment is posted so it is not silent

## HTTP API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Process is up |
| GET | `/health/llm` | LM Studio reachable |
| GET | `/repos` | Registered agents |
| GET | `/repos/{owner}/{name}` | One agent brief |
| POST | `/repos` | Register / update an agent |
| GET | `/jobs/{id}` | Webhook job status |
| POST | `/webhooks/github` | GitHub webhook |

## Tests

```bash
pytest
```

No live GitHub or LM Studio required.

## Config

| Env | Default | Meaning |
|---|---|---|
| `GITHUB_WEBHOOK_SECRET` | required | HMAC secret |
| `GITHUB_TOKEN` | required | PAT |
| `LLM_BASE_URL` | `http://127.0.0.1:1234/v1` | LM Studio OpenAI-compat URL |
| `LLM_API_KEY` | `lm-studio` | Ignored by LM Studio, required by the client |
| `LLM_MODEL` | empty | Empty = first loaded model |
| `MAX_FILES` | `30` | Files reviewed per PR |
| `MAX_PATCH_CHARS` | `20000` | Skip larger file patches |
| `LLM_TIMEOUT_SECONDS` | `180` | Per completion |
| `REPOS_FILE` | `repos.yaml` | Agent registry |
| `ALLOW_UNREGISTERED` | `false` | Auto-create agents on first webhook |

Jobs are in-memory. A process restart drops in-flight reviews.
