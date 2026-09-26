# 01 – Niche exploration

How the idea evolved, including the directions I passed on.

## Rejected: verifiable terminal/CLI micro-tasks

Repairing configs, fixing merge conflicts, patching flaky tests, cleaning malformed data files. A Docker container plus a deterministic checker, no GPU needed.

**Why rejected:** already done. Terminal-Bench, Endless Terminals, SETA and others generate these at scale.

## AI-safety-flavored environments

All text/code only, no simulator.

1. **Sabotage / control evals.** One policy does a normal coding or ops task while secretly trying to insert a backdoor or sandbag; a second "monitor" policy has to catch it. Upstream of the AI-control research agenda; few open environments exist.
2. **Steganographic collusion.** Two agents try to pass a hidden payload past an overseer reading their outputs. Reward = payload delivered minus overseer suspicion.
3. **Calibrated betting / adversarial forecasting.** Agents wager on their own correctness or on each other's claims, scored with a proper scoring rule. Rewards good epistemics, not just task completion.

**Tradeoff:** less saturated than task-completion envs, but harder to grade cleanly. Needs rubrics or game-theoretic payoffs instead of pass/fail.

## Automated mechanistic interpretability

Train a tiny toy model (a 1–2 layer transformer on modular arithmetic, or an MLP with a planted feature) where the ground-truth circuit is known because I built it in. The agent has to find and explain the mechanism: which heads/neurons implement it, what feature makes an activation fire.

- **Reward is transparent:** graded against the planted answer, not an LLM judge.
- **Compute is trivial:** toy models train in seconds on CPU.
- **Tradeoff:** the design effort moves to hand-building models with known, verifiable circuits (superposition puzzles, induction heads, planted backdoor features). It stays cheap only while the models stay tiny.

Example first tasks:
- Find the planted feature in a toy sparse autoencoder.
- Reverse-engineer a 2-layer transformer trained on modular addition.
