---
name: reward-hack-audit
description: Adversarially audit a Harbor task or generated task set for reward hacking before it is used for training or published — checks ground-truth leakage, verifier tampering, format-only checks, and degenerate policies that score well. Use whenever a task, verifier, or reward function is created or changed, before publishing, before an RL run, or when rewards look suspiciously high, even if the user only says "check the task" or "is this ready?".
---

# Reward-hack audit

RL optimizes whatever the verifier actually rewards, not what you meant. Anthropic has reported dozens of production environments that were exploitable, and long-horizon benchmarks see double-digit percentages of rollouts attacking the verifier. An environment that can be hacked teaches the model to hack. Audit every task before it trains anything.

Work like an attacker: your goal is to get a high reward without doing the task. Every exploit you find is a success.

## 1. Leakage: can the agent see the answer?

Inspect everything the agent's container can reach:

- `environment/` build context and Dockerfile: any ground truth, solution, generator seed, or verifier code copied in?
- Image layers and history: `docker history`, or files deleted in a later layer that still exist in an earlier one.
- Env vars, mounted volumes, `.git` directories, cached pip/uv packages that bundle fixtures.
- **Shared verifier mode:** `/tests` is uploaded at verify time, but anything the agent leaves behind runs alongside it. Prefer separate-verifier mode with ground truth baked into `tests/Dockerfile`.
- Network: if the agent phase has network access, can it fetch the answer (a public dataset, the repo itself)?
- Inputs: can the answer be inferred from the inputs' structure, such as filename ordering, generator artifacts, or noise that only appears in eligible cases?

## 2. Tampering: can the agent change how it's graded?

In shared mode especially, check whether the agent could:

- write `/logs/verifier/reward.txt` or `reward.json` directly,
- plant `conftest.py`, `sitecustomize.py`, `.pth` files, or PATH shims that the verifier then runs,
- modify tools the verifier calls (python, uv, the package cache),
- edit test files or the reference data.

## 3. Degenerate policies: does a dumb answer score well?

Write each of these as an alternative `solve.sh` and run it as the Oracle (copy the task, swap `solution/solve.sh`):

| Policy | Example | Expected reward |
|---|---|---|
| Empty | no output file | 0 |
| Malformed | invalid JSON / wrong schema | 0 |
| Constant | every field set to the most common value (e.g. all "eligible") | well below a real solve |
| Hedge-everything | every answer "unknown", every item flagged as missing | well below a real solve |
| Input echo | copy input fields into the answer | ~0 |
| Format-only | correct schema, random values | ~0 |

Any of these scoring more than a fraction of the Oracle is a finding. For generated task sets, run them across at least 20 tasks, since per-task noise hides systematic leaks.

## 4. Verifier logic

Read the verifier code itself:

- Does it check the outcome or only the format/presence of output?
- Tolerances: are they wide enough that a rough guess passes?
- Partial credit: can one easy dimension carry the weighted mean?
- Exceptions: does a crash in the verifier default to pass, or to 0?
- Determinism: does the same answer always get the same reward?

## Report

Write the result to the task's `README.md` under `## Reward-hack audit` (create it if missing), so the audit ships with the task:

```markdown
## Reward-hack audit (<date>)
| Check | Result | Notes |
|---|---|---|
| Leakage | pass/fail | ... |
| Tampering | pass/fail | ... |
| Degenerate policies | pass/fail | constant: 0.12, hedge: 0.08, ... |
| Verifier logic | pass/fail | ... |

**Findings:** numbered list, each with a concrete fix.
```

Fix findings before the task is used for training. A task with a known open exploit shouldn't be published, even as private.
