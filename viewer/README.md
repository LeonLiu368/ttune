# viewer

A web page for ttune's eval runs. It shows every run's scores on typical (ID) and unusual (OOD) households, then lets you open any single household and see what the model said next to PolicyEngine's answer. With the server running, it can also start new runs.

It works two ways, with the same pages:

| | Command | What you get |
|---|---|---|
| Read-only site | `python -m viewer build --out _site` | Static files. GitHub Pages publishes them from `main` (see below). |
| Live server | `python -m viewer serve` | The same pages, plus an API that starts eval runs on GitHub Actions. |

The page checks which one it's talking to. The top bar says **Read-only** or **Live server**, and the launch form only turns on with the live server.

## What's on the pages

- **Runs:** every run in `evals/results/`, newest first, with ID and OOD reward, false denials and malformed replies. The launch form is here too.
- **One run:**
  - reward on each set and the change, with its 95% interval
  - the floors (what answering "no" or "yes" to everything would score)
  - balanced accuracy and false denials by program
  - the OOD set by shift family and by twist
  - a table of all 400 households you can filter (perfect, reward 0, false denials, malformed, cut off)
- **One household:** the case text the model saw; a table of the model's answer against PolicyEngine's for each program and member, each marked right, false denial or false approval; the scores; and the model's full reply.

Model replies are shown as plain text, never as HTML, because they're untrusted.

## Run it locally

```bash
pip install -r requirements.txt
python -m viewer serve                       # http://127.0.0.1:8000, launching off
```

To launch runs from the page, give the server a GitHub token that can run Actions on the repo. Use a fine-grained token with **Actions: read and write** on `LeonLiu368/ttune`:

```bash
export VIEWER_GITHUB_TOKEN=...               # never commit it
python -m viewer serve
```

The form sends `POST /api/runs`. The server checks every input, then starts the **Eval (self-hosted model)** or **Eval** workflow. When the run finishes, the workflow opens a results PR. Merge it, and the run appears on the page.

| Setting | Meaning |
|---|---|
| `VIEWER_GITHUB_TOKEN` | Turns launching on. Without it the server is read-only. |
| `VIEWER_LAUNCH_KEY` | A shared secret the form must send. **Required** before the server listens beyond this machine (`--host 0.0.0.0`). |
| `VIEWER_ALLOW_PAID=1` | Allows paid OpenRouter models. Off by default; the eval workflow's own cost guard still applies. |
| `VIEWER_REPO` | Which repo to launch on. Default `LeonLiu368/ttune`. |

## API

| Endpoint | Returns |
|---|---|
| `GET /api/health` | `{"server": true, "launch": …, "presets": […], …}` |
| `GET /api/launches` | The latest eval workflow runs on GitHub |
| `POST /api/runs` | Starts a run. Self-hosted body: `{"backend": "self-hosted", "preset", "limit", "shards", "max_tokens"}`. OpenRouter body: `{"backend": "openrouter", "model", "limit", "max_tokens", "reasoning_effort", "allow_paid"}`. Returns 202. |
| `GET /data/runs.json` and `/data/runs/<run>/…` | Run data, as described in [`data.py`](data.py) |

## GitHub Pages

The **Viewer site** workflow rebuilds the read-only site whenever results or the viewer change on `main`, and publishes it at `https://leonliu368.github.io/ttune/`. It needs a one-time setting: **Settings → Pages → Build and deployment → Source: GitHub Actions**.

## Putting the server in the cloud (later)

The server is a single Python process that uses only the standard library and `httpx`. It reads results from its checkout of the repo. To host it:

1. Run `git pull` on a schedule, or after each results PR merges, so new runs appear.
2. Serve it over HTTPS behind a proxy, with `--host 0.0.0.0`.
3. Set `VIEWER_LAUNCH_KEY`. The server refuses to listen beyond the machine without one.
4. Keep `VIEWER_GITHUB_TOKEN` in the host's secret store.

Before anyone else gets the URL, add real sign-in instead of the shared key.
