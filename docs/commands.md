# Commands

Every command runs as `python -m <package> <command>` from the repository root. `--help` on any command or subcommand prints its full options; a test checks that all 29 render.

| Needs | Install |
|---|---|
| Most commands | `pip install -r requirements.txt` |
| Documents, PDFs, tasks | `pip install -r requirements-docgen.txt` |
| Anything that computes answers (envgen, the calculator, splits, scripted demonstrations) | `pip install -r requirements-envgen.txt` (policyengine-us 2.50.1) |
| Serving a model locally | `pip install -r requirements-local-llm.txt` (llama.cpp server) |
| Rendering a document's text | `pdftotext`, from poppler-utils |
| Running tasks | Docker, and [Harbor](https://github.com/laude-institute/harbor) 0.25.0 (`uv tool install harbor==0.25.0`) |

## scraper: official sources

| Command | What it does |
|---|---|
| `scraper status` | Show each source in `data/sources.json` and its latest snapshot |
| `scraper fetch [--source ID] [--ci]` | Download sources into dated snapshots in `data/raw/`. `--ci` skips sources that must be fetched by hand. |
| `scraper import ID FILE... [--url URL]` | Snapshot files you downloaded by hand, for sites that block the scraper |
| `scraper extract [--source ID]` | Parse the latest snapshots into `data/processed/<id>.csv` |
| `scraper check [--source ID] [--show N]` | Compare processed values with PolicyEngine; writes `data/processed/checks/` |

## envgen: households

| Command | What it does |
|---|---|
| `envgen generate --set {id,ood} [--n N] [--seed S] [--out DIR]` | Write a household set with PolicyEngine's answers (default `data/households/<set>/`). The published sets use 200 households, seed 1. |

## docgen: document packets

| Command | What it does |
|---|---|
| `docgen build --set {id,ood}` | Write each household's documents, distractors, gaps and the truth that follows them, to `data/documents/<set>/cases.jsonl` |
| `docgen pdf --set {id,ood} [--ids ...] [--out DIR]` | Render a built set's documents as PDFs |

## harbortask: Harbor tasks

| Command | What it does |
|---|---|
| `harbortask build --samples` | Rebuild the 6 sample tasks in `tasks/` (CI checks they match) |
| `harbortask build --set {id,ood} [--ids ...] --out DIR` | Build tasks for every case in a set, or the listed ones |
| `harbortask split --split {train,validation,holdout-id,holdout-ood} [--n N] --out DIR` | Build a whole split. Train and validation read the secret from `TTUNE_TRAIN_SEED`. |
| `harbortask audit` | Score degenerate answers (empty, all yes, all no, random…) on all 400 document cases; writes `tasks/audit.json` |
| `harbortask agentic pick --out DIR [--limit N] [--shard K/N]` | Build one shard's holdout tasks. `--split train --start S` builds training tasks instead. |
| `harbortask agentic show JOB_DIR` | Print a Harbor trial: its rewards, `answer.json` and every agent turn |
| `harbortask agentic collect RUN_ID --jobs DIR... --model M [--compare-to RUN]` | Score Harbor trials into an evals run in `evals/results/RUN_ID/` |
| `harbortask scripted --split {train,validation} --out FILE` | Write the scripted SFT demonstrations for a secret split |
| `harbortask scripted --holdout {id,ood} --limit N --out FILE` | The same for public holdout cases, to preview or test |
| `harbortask teacher price --model M --out FILE` | The teacher model's OpenRouter price, refusing one above the ceiling |
| `harbortask teacher can-start --jobs DIR --prices FILE --budget USD` | Exit 0 if one more task fits in the budget, 3 if not |
| `harbortask teacher sft --jobs DIR... --out FILE` | The teacher's good trials as chat transcripts |
| `harbortask teacher summary --jobs DIR... --prices FILE --model M --out FILE` | Aggregate numbers only, safe to publish |

Inside a task's container, the agent also has:

| Command | What it does |
|---|---|
| `pdftotext -layout /app/case/<file>.pdf -` | Print a document's text |
| `benefits-calc household.json` | PolicyEngine on the household's facts. `--example` prints a sample input and `--help` describes the format. |

## evals: one-reply evaluation

| Command | What it does |
|---|---|
| `evals run --set {id,ood} --model M [--limit N] [--base-url URL] [--households FILE] [--shard K/N]` | Run a model over a set and score it. `--households data/documents/<set>/cases.jsonl` uses the paperwork instead of summaries. |
| `evals merge RUN_ID --parts DIR...` | Combine shard results into one run, checking that every household appears once |
| `evals rescore RUN_ID` | Score a run's stored replies again with the current scorer (no model calls) |
| `evals compare RUN_ID` | Write `comparison.md`: ID vs OOD with bootstrap intervals, per program and per OOD family |
| `evals model {resolve,fetch} PRESET` | Find or download an open model from `evals/local_models.json`, checking its SHA-256 |
| `evals preflight --model M [--allow-paid]` | The cost guard: refuse a paid OpenRouter model unless allowed |

To run a self-hosted model locally:

```bash
python -m evals model fetch qwen3-4b-instruct --models-dir models
python -m llama_cpp.server --model models/<file>.gguf --model_alias local/qwen3-4b-instruct \
  --n_ctx 12288 --logits_all False --port 8000 &
python -m evals run --set id --limit 5 --model local/qwen3-4b-instruct --base-url http://127.0.0.1:8000/v1 \
  --timeout 1800 --max-tokens 6000
python -m evals compare <run id>
```

## viewer: the results site

| Command | What it does |
|---|---|
| `viewer build [--out DIR]` | Write the static site from `evals/results/` (default `_site/`) |
| `viewer serve [--port P]` | Serve the viewer locally, plus a launch form that starts eval runs on GitHub Actions ([viewer/README.md](../viewer/README.md)) |

## Other

| Command | What it does |
|---|---|
| `python -m pytest -q` | All tests; the PolicyEngine and `pdftotext` tests skip when those aren't installed |
| `python sft/tools/make_colab_notebook.py sft/colab_sft.ipynb` | Regenerate the Colab notebook from its script (a test checks they match) |
