# SFT warm-start

The agentic baseline showed Qwen3 4B can't use the environment yet: it answers "unknown", greps the PDFs and never runs `benefits-calc` ([ROADMAP](../ROADMAP.md#agentic-baseline-qwen3-4b-instruct-with-harbors-terminus-2-0)). RL from there would see almost no reward, so it first learns from a stronger model's good runs.

## Teacher trajectories

The **Teacher trajectories** workflow (run by hand, costs money) runs a stronger open model through Harbor's `terminus-2` agent on the secret training tasks:

- **Teacher:** Qwen3 235B Instruct (2507) on OpenRouter, under Apache 2.0, so training on its outputs is allowed. It's the same family and chat format as the 4B student.
- **Only training tasks:** it runs on the 1,000 training households built from the `TTUNE_TRAIN_SEED` secret (`python -m harbortask agentic pick --split train`), never on the holdout.
- **Spending:**
  - The run refuses a teacher priced above the ceiling in `harbortask/teacher.py`.
  - Before every task, each shard checks that its share of `budget_usd` still covers the most one task can cost.
  - Spend is counted from token counts, with cache reads priced as input, so it errs high.
- **Privacy:**
  - The trajectories reveal training answers, so the public logs show only rewards and turn counts.
  - The trials and the SFT file are kept as an artifact encrypted with the secret, the same way as the splits.
  - Only the aggregate summary in [`teacher/`](teacher/) is committed.
- **The SFT file:** `bundle/sft.jsonl` in the artifact holds one chat transcript per kept trial (`python -m harbortask teacher sft`). A trial is kept if it:
  - scored at least 0.9;
  - finished without a timeout;
  - was never summarized, so it is one linear conversation.

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:TTUNE_TRAIN_SEED \
  -in ttune-teacher.tar.gz.enc | tar -xzf -        # -> bundle/sft.jsonl, bundle/trials/
```
