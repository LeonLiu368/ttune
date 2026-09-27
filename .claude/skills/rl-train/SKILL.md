---
name: rl-train
description: Plan and run a low-compute fine-tuning / RL loop on ttune's Harbor environments — baseline eval, train/holdout splits, SFT warm-start from trajectories, GRPO, and monitoring for reward hacking. Use whenever the user wants to train, fine-tune, RL, or evaluate a model on the ttune environments, pick a base model or training library, estimate compute, or read training results, even if they just say "let's train it".
---

# RL training on ttune environments

The loop: measure a baseline, warm-start with SFT, improve with RL against the Harbor verifier, and keep checking the model is learning the task rather than the verifier. Constraint: little compute. Small open-weight models (4–8B), LoRA, one rented GPU or a hosted fine-tuning API.

Training libraries and hosted APIs change quickly. Check the current docs of whichever one is chosen for exact APIs instead of relying on memory, and say which version you checked.

## 0. Preconditions

Don't start training until these hold. Each one has sunk real RL runs:

- Every task in the training set passes its Oracle run (reward ~1.0).
- The `reward-hack-audit` skill has been run on the generator and its findings are fixed.
- The splits exist (step 1).

## 1. Splits

Split by structure, not at random, so the holdout measures generalization instead of memorization:

- **train**: most states / programs / household types.
- **holdout-id**: unseen seeds from the same distribution.
- **holdout-ood**: whole states or programs never seen in training.

Freeze holdouts before any training and never tune on them.

## 2. Baseline

Run the base model, plus one stronger reference model, on both holdouts with `harbor run` and record per-dimension rewards, not just the mean. For the benefits env, track the false-"not eligible" rate separately; it's the metric that matters most (see docs/04).

## 3. SFT warm-start

Small models often score near zero at first, and RL can't learn from all-zero rewards. Warm-start them:

1. Run a strong model on train tasks. Harbor saves each attempt's trajectory at `agent/trajectory.json` (ATIF format) next to its verifier result.
2. Keep only trajectories with high reward (e.g. ≥ 0.9) and no audit flags. Target about 1–2k.
3. Check the strong model's terms allow training on its outputs before using them.
4. LoRA SFT on those trajectories, then re-run the baseline evals.

## 4. RL (GRPO)

- Sample several attempts per task (a group of 4–8) and use reward within the group as the advantage. That's GRPO's core idea, and it's why tasks need a spread of difficulty: groups where every attempt scores the same teach nothing.
- Use the Harbor verifier's reward, with the per-dimension weights from the env's plan doc.
- Candidate stacks: TRL's GRPO trainer, verl, or SkyRL on one rented GPU, or a hosted fine-tuning API (e.g. Tinker) to avoid managing GPUs. Pick based on whether the library can drive multi-turn tool-using agents in containers, which is the hard requirement here.
- Keep the KL penalty / reference model on at first; turning it off is an experiment, not a default.

## 5. Monitoring

Watch these every eval interval (e.g. every 50 steps):

- Holdout reward by dimension. Train reward rising while holdout-ood flat means memorization.
- Degenerate-policy signatures: answers getting more uniform, "unknown" rate rising, output length collapsing.
- A sample of trajectories read by a human (or a separate model) each interval. Reward curves don't show hacking; transcripts do.
- Any exploit found goes into the generator/verifier fix list and the `reward-hack-audit` report; retrain from the last clean checkpoint instead of continuing.

## 6. Record results

Append each run to `docs/06-training-log.md` (create it if missing) with: date, base model, library + version, config (LoRA rank, lr, group size, steps), compute used and cost, baseline vs final on both holdouts by dimension, and anything that went wrong. Keep failed runs; they're as useful as successful ones.
