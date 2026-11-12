# viewer

A web page for ttune's experiments, tasks and eval runs. It shows every run's scores on typical (ID) and unusual (OOD) households. You can search the tasks, open any task's real files (the PDFs drawn as the agent gets them), and step through what a model did on it, next to PolicyEngine's answer. With the server running, it can also start new runs.

It works two ways, with the same pages:

| | Command | What you get |
|---|---|---|
| Read-only site | `python -m viewer build --out _site` | Static files. GitHub Pages publishes them from `main` (see below). |
| Live server | `python -m viewer serve` | The same pages, plus an API that starts eval runs on GitHub Actions. |

The page checks which one it's talking to. The top bar says **Read-only** or **Live server**, and the launch form only turns on with the live server.

## What's on the pages

- **Experiments** (the home page): runs grouped by how they worked, so they rank side by side. Agent runs, one reply from the paperwork, and one reply from a written summary are the three today. [`evals/experiments.json`](../evals/experiments.json) names them and lists their runs; a new run joins one by kind if it isn't listed.
- **One experiment:**
  - summary cards: mean reward, trials finished (pass, partial, fail, error, not run), tasks, cost and tokens;
  - a leaderboard of its runs;
  - a grid of every task against every run, one square per trial. Search it (comma-separated terms), filter by trial status or view (any error, any failed, all failed), pick columns, and copy it as TSV. A square opens that trial.
- **Tasks:** every task with its household, distractors and gaps, PolicyEngine's answer, and a square for each run that scored it. Search it, and filter by split, shift family, twist, issue, state, PolicyEngine's answer, experiment or latest result.
- **One task**, split in two like a code review:
  - **Task definition:** the task's files as Harbor runs them: instruction (rendered or raw), each document PDF (drawn with pdf.js, or as the text the agent can extract), the reference solution, the answer key and verifier, the agent's environment and `task.toml`. An Overview lists the household, issues and answer.
  - **Trial:** pick any run's trial. Summary has the execution timeline (environment setup, agent, verifier) and the scores. Answer has the model's answer against PolicyEngine's. Trajectory has every agent step: its analysis and plan, the commands it typed, the terminal output and tokens.
- **Runs:** every run in `evals/results/`, newest first, with ID and OOD reward, false denials and malformed replies. The launch form is here too.
- **One run:**
  - reward on each set and the change, with its 95% interval
  - the floors (what answering "no" or "yes" to everything would score)
  - balanced accuracy and false denials by program
  - the OOD set by shift family and by twist
  - a table of all 400 households you can filter (perfect, reward 0, false denials, malformed, cut off)
- **One household:** the case text the model saw; a table of the model's answer against PolicyEngine's for each program and member, each marked right, false denial or false approval; the scores; and the model's full reply.

Model replies and trajectories are shown as plain text, never as HTML, because they're untrusted.

### What gets published

Only the 400 holdout tasks: their answers are already in this repo. The 1,000 train and 200 validation tasks have secret answers, and their documents alone are enough to work those out, so the static build never includes them. To browse them, decrypt a **Task splits** artifact ([docs/workflows.md](../docs/workflows.md#privacy-rules)) and start a local server on it:

```bash
python -m viewer serve --private-splits build/splits     # holds train/ and validation/; refused beyond 127.0.0.1
```

Agent trajectories come from `evals/results/<run>/trajectories/`. `harbortask agentic collect` writes them for every new agent run, and the **Trajectories (backfill)** workflow adds them to an older run while its artifacts last.

## Run it locally

```bash
pip install -r requirements-docgen.txt      # reportlab draws the task PDFs
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
| `GET /data/experiments.json`, `/data/experiments/<id>.json` | Experiments, as described in [`explore.py`](explore.py) |
| `GET /data/tasks.json`, `/data/tasks/<task>/task.json`, `/data/tasks/<task>/files/<path>` | Tasks, their files (built on first use), and their trials |
| `GET /data/runs/<run>/trajectories/<task>.json.gz` | One trial's agent turns |

## GitHub Pages

The **Viewer site** workflow rebuilds the read-only site whenever results, tasks or the viewer change on `main` (about two minutes, most of it drawing 400 tasks' PDFs), and publishes it at `https://leonliu368.github.io/ttune/`. It needs a one-time setting: **Settings → Pages → Build and deployment → Source: GitHub Actions**.

## Putting the server in the cloud (later)

The server is a single Python process that uses only the standard library and `httpx`. It reads results from its checkout of the repo. To host it:

1. Run `git pull` on a schedule, or after each results PR merges, so new runs appear.
2. Serve it over HTTPS behind a proxy, with `--host 0.0.0.0`.
3. Set `VIEWER_LAUNCH_KEY`. The server refuses to listen beyond the machine without one.
4. Keep `VIEWER_GITHUB_TOKEN` in the host's secret store.

Before anyone else gets the URL, add real sign-in instead of the shared key.
