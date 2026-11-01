# Harbor tasks

Each task gives an agent one household's paperwork and a PolicyEngine calculator, and scores the `/app/answer.json` it writes. Tasks are built from the document cases in [`data/documents`](../data/documents/README.md) by `harbortask/`. Don't edit them by hand.

This folder holds 6 hand-checked sample tasks:

| Task | Case | What it tests |
|---|---|---|
| [benefits-5e5278f3df](benefits-5e5278f3df/) | id-1-0001 | A typical household, no injected issue |
| [benefits-3111a2acb3](benefits-3111a2acb3/) | id-1-0003 | A partner who moved out, still named on the lease |
| [benefits-ca5c448e40](benefits-ca5c448e40/) | id-1-0002 | Missing pay stubs (a gap) |
| [benefits-e41833f6c8](benefits-e41833f6c8/) | id-1-0008 | The lease page with the rent is missing (a gap) |
| [benefits-ad9f0b012e](benefits-ad9f0b012e/) | id-1-0079 | No childcare receipt (a gap) |
| [benefits-145a2b74d9](benefits-145a2b74d9/) | ood-1-0000 | A multigenerational household with a stale pay stub |

The full generated set, with train and holdout splits, is described under [Splits](#splits).

## Splits

The tasks a model trains on are generated separately from the sample tasks here, by `python -m harbortask split`:

| Split | Households | Source | Answers |
|---|---|---|---|
| `train` | 1,000 | Fresh typical households (envgen's ID sampler), seeded from the `TTUNE_TRAIN_SEED` secret | Private |
| `validation` | 200 | The same sampler, from a second seed derived from the same secret | Private |
| `holdout-id` | 200 | The published typical cases, [`data/documents/id`](../data/documents/id/) | Public; never trained on |
| `holdout-ood` | 200 | The published unusual cases, [`data/documents/ood`](../data/documents/ood/) | Public; never trained on |

- **Why typical households only.** Training uses typical households only, so the OOD holdout measures true generalization: does practice on typical paperwork carry over to unusual households? The eval numbers so far come from the same 400 holdout cases, so they stay comparable.
- **Keeping the answers private.** A public seed would let anyone regenerate the training answers.
  - Each generated case is renamed `train-0001`, `validation-0001` and so on, and its seed is blanked, so no file reveals the seed.
  - The build fails if any generated household has the same facts as another or as a holdout household.
- **Checks on every build.** Each split gets the reward-hack audit, and the balance check stops the build if a program comes out all one answer.

The **Task splits** workflow (run by hand) does all of this:

1. Builds the four splits.
2. Runs the Oracle in Docker on a sample of the generated tasks.
3. Uploads the tasks encrypted with the secret. Artifacts of a public repo can be downloaded by any GitHub user, so they're never uploaded in the clear.
4. Opens a PR with the manifests in [`splits/`](splits/): counts, audit and task digests, with no case data or answers.

### The current build

Run [41242886804](https://github.com/LeonLiu368/ttune/actions/runs/41242886804), 2026-10-31, generator commit `3ba7556`. The encrypted tasks are in the artifact `ttune-splits-41242886804` (42 MB), kept until 2027-01-29.

| Split | Tasks | Packets with a gap | SNAP yes / no / unknown | Oracle | Best degenerate answer |
|---|---|---|---|---|---|
| `train` | 1,000 | 338 | 433 / 383 / 184 | 1.0 | 0.36 (all no) |
| `validation` | 200 | 82 | 81 / 73 / 46 | 1.0 | 0.35 (all no) |
| `holdout-id` | 200 | 77 | 76 / 84 / 40 | 1.0 | 0.38 (all no) |
| `holdout-ood` | 200 | 48 | 92 / 86 / 22 | 1.0 | 0.38 (all yes) |

- **Oracle in Docker:** Harbor's Oracle scored 1.0 on every dimension of 4 sampled tasks (3 train, 1 validation).
- **Audit:** the reward-hack audit passed on every split. Empty and malformed answers scored 0.
- **Overlap:** no train or validation household repeats another household or a holdout one.
- **Details:** the per-program answers, issue counts and task digests are in the [manifests](splits/).

To build a split yourself, or to open the workflow's artifact:

```bash
export TTUNE_TRAIN_SEED=...      # the repository secret; never commit it
python -m harbortask split --split train --n 1000 --out build/splits
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:TTUNE_TRAIN_SEED \
  -in ttune-splits.tar.gz.enc | tar -xzf -                     # -> splits/<split>/<task-id>/
harbor run -p splits/train -a <agent> -m <model> -e docker     # a whole split as one Harbor job
```

## How a task works

- **The agent's container:**
  - `/app/case/*.pdf` holds the application and documents, and `pdftotext` can read them.
  - `benefits-calc` is PolicyEngine as a calculator: the household's facts as JSON in, SNAP, EITC, Medicaid and WIC out. It runs the same code that wrote the answer key, so correct facts give the right answer. The skill is reading the paperwork, applying the stated rules, and spotting what's missing.
  - No network. The agent runs as a non-root user.
- **The verifier:**
  - A separate, offline container built from `tests/` (Reward Kit 0.2.3) holds the answer key and the grading code.
  - Only `/app/answer.json` crosses over.
- **The answer:** each program's eligibility and amounts, `unknown` where a missing document could change the answer, and `missing_information`, a list of documents to request, each from a fixed list of 8 kinds.

| Dimension | Weight | Scoring |
|---|---|---|
| `eligibility` | 0.60 | As in the evals (`evals/score.py`): a wrong "not eligible" costs double; "unknown" is right only where a gap leaves the decision open |
| `amount` | 0.25 | SNAP and EITC amounts when truly eligible: full credit within 5% or $10, zero at 25% off. With no amount to score, it equals eligibility |
| `missing_info` | 0.15 | Share of the truly missing documents listed, minus 0.25 per wrong item |
| `reward` | | Weighted mean |

## Commands

```bash
pip install -r requirements-docgen.txt
python -m harbortask audit                              # degenerate answers over all 400 cases -> tasks/audit.json
python -m harbortask build --samples                    # the 6 tasks here
python -m harbortask build --set ood --out /tmp/tasks   # every case in a set
harbor run -p tasks/benefits-5e5278f3df -a oracle -e docker    # needs Docker; reward should be 1.0
```

The **Harbor tasks** workflow does the last step for every task on each change, in Docker, and checks that a copy with an empty answer scores 0. It also checks that `tasks/` matches what the generator writes.

### The agentic baseline

The **Baseline (Harbor agent, self-hosted model)** workflow runs a real agent on the holdout tasks, for $0. An open model (Qwen3 4B by default) is served by llama.cpp on the runner's CPU and drives Harbor's `terminus-2` agent in each task's offline container. A final job scores every trial and opens a PR with an evals run in `evals/results/`:

- **Two scores for each answer:** the evals scorer, which lines up with the one-shot runs on the same households, and the task's own reward, which adds the missing-information list. The report also checks that the second matches what Harbor's verifier reported.
- **Failures:** an agent that times out or writes no answer scores 0. A trial that never reached the verifier, or a task the shard ran out of time for, is counted as an error and not scored.
- **The report:** comparison.md shows the agent's numbers (timeouts, turns, minutes per task) and a same-household comparison with the one-shot document run.

```bash
python -m harbortask agentic pick --out build/tasks --limit 5 --shard 0/2     # build one shard's holdout tasks
harbor run -p build/tasks/<task> -a terminus-2 -m openai/<model> --ak api_base=<server>/v1 -e docker
python -m harbortask agentic collect <run id> --jobs jobs/ --model <model> --limit 5   # -> evals/results/<run id>
```

The task image includes `tmux`, which terminal agents need and can't install themselves without a network. The manifests in [`splits/`](splits/) were built before tmux was added, so their task digests are out of date until the **Task splits** workflow runs again.

## Reward-hack audit

Run on 2026-10-31 over all 400 document cases (`python -m harbortask audit`), scoring each policy with the verifier's own code:

| Policy | Mean reward | Max | Eligibility | Amount | Missing info |
|---|---|---|---|---|---|
| Reference answer | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Empty (no answer file) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| Malformed JSON | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| All "no", flag nothing | 0.33 | 1.00 | 0.28 | 0.26 | 0.69 |
| All "yes", flag nothing | 0.33 | 0.71 | 0.37 | 0.02 | 0.69 |
| All "unknown", flag everything | 0.08 | 0.77 | 0.10 | 0.09 | 0.00 |
| Right format, random values | 0.28 | 1.00 | 0.26 | 0.16 | 0.52 |

- **Blanket answers sit at the same floor as in the evals (about 0.33).** Their maximum hits 1.0 only on households that truly qualify for nothing and have nothing missing, where "no" is the right answer.
- **Flagging nothing is right 69% of the time,** because 69% of packets have no gap. That's why those policies keep their missing-info score. Flagging everything, or hedging everything as "unknown", scores 0.08.

| Check | Result | Notes |
|---|---|---|
| Leakage | pass | The agent image holds only the PDFs and `benefits-calc`. The answer key, grading code and reference solution are in the verifier image or `solution/`. Neither container has network. Task ids are hashes, not case ids. Checked by `tests/test_harbortask.py`. |
| Tampering | pass | Separate verifier container; only `/app/answer.json` crosses over, and it's read as data. |
| Degenerate policies | pass | The table above. |
| Verifier logic | pass | It scores outcomes (answers against PolicyEngine), not format. Missing or unreadable answers and grading errors score 0. Deterministic. |

**Findings:**

- **Base images aren't pinned by digest yet.** `harbor lint --select ALL` reports `unpinned-image`. Pin `python:3.12-slim` to a digest once one is chosen in CI.
- **The case data is public in this repo.** That's safe only because both containers are offline and task ids are hashed. A harness that gives the agent network access would let it look answers up, so tasks used for training should come from households that aren't published.
