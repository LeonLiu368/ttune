# 05 – Skills

Claude Code skills for working in this repo. They live in [`.claude/skills/`](../.claude/skills/) and load automatically when Claude Code runs in ttune. Each one triggers from its description, or you can call it by name (e.g. `/benefits-task`).

## How they fit together

```
new idea ──► env-idea-scorecard ──► go?
                                     │
                                     ▼
          benefits-task (domain) + create-task / rewardkit (Harbor mechanics)
                                     │
                                     ▼
                           reward-hack-audit ──► fix findings
                                     │
                                     ▼
                  rl-train (baseline → SFT → GRPO → monitor)
                                     │
                                     ▼
                           publish (Harbor Hub)
```

## Original to ttune

| Skill | Use it when | Writes to |
|---|---|---|
| [`env-idea-scorecard`](../.claude/skills/env-idea-scorecard/SKILL.md) | Evaluating a new environment idea. Scores it 1–5 on verifiability, compute, saturation, realism, generatability, hack-resistance and impact, checks Harbor's registry for overlap, and gives a go / maybe / no-go. | `docs/02` → `## Scored ideas` |
| [`benefits-task`](../.claude/skills/benefits-task/SKILL.md) | Building the benefits-eligibility environment: household generator, messy documents, PolicyEngine ground truth, answer schema, asymmetric reward. | Task directories |
| [`reward-hack-audit`](../.claude/skills/reward-hack-audit/SKILL.md) | Before any task is trained on or published. Checks for answer leakage, verifier tampering and degenerate answers that score well (all-eligible, hedge-everything, format-only), plus verifier logic. | Each task's `README.md` → `## Reward-hack audit` |
| [`rl-train`](../.claude/skills/rl-train/SKILL.md) | Training a model on the environments: splits, baseline, SFT warm-start from Harbor trajectories, GRPO, monitoring for hacking. | `docs/06-training-log.md` |

## Pulled in from Harbor

Copied unmodified from [harbor-framework/harbor](https://github.com/laude-institute/harbor) under Apache-2.0; source commit and license are in [`.claude/skills/THIRD_PARTY.md`](../.claude/skills/THIRD_PARTY.md).

| Skill | What it covers |
|---|---|
| [`create-task`](../.claude/skills/create-task/SKILL.md) | Scaffolding a Harbor task end-to-end: `harbor task init`, instruction, Dockerfile, verifier choice, `task.toml`, network policy, Oracle runs, multi-step tasks |
| [`rewardkit`](../.claude/skills/rewardkit/SKILL.md) | Writing verifiers with Reward Kit: built-in checks, custom `@criterion` functions, LLM/agent judges, multi-dimension rewards and aggregation |
| [`publish`](../.claude/skills/publish/SKILL.md) | Publishing tasks and datasets to Harbor Hub |

Harbor also ships `harbor-exec` (map-reduce over loose inputs), `create-adapter` (porting existing benchmarks) and `upload-parity-experiments`. They aren't needed yet; copy them from upstream if that changes.

## Already on my claude.ai account

These are enabled on my account and available in any session. The useful ones here:

| Skill | Use in ttune |
|---|---|
| `pdf` | Rendering realistic documents for task fixtures (pay stubs, leases, benefit letters), including scan-like PDFs |
| `xlsx` | Spreadsheet fixtures (e.g. for the accounting-close idea) and results tables |
| `skill-creator` | Testing and improving the skills above: running them on test prompts, benchmarking against no-skill baselines, tuning descriptions so they trigger reliably |
| `docs` | Turning a plan doc into a shareable, commentable page if others need to review it |

The rest (`docx`, `pptx`, `google-workspace`, `morning`, `import-memory`) aren't relevant to this project.

## Status

The four original skills are first drafts written from the plans in docs 01–04. They haven't yet been tested with `skill-creator`'s evaluation loop. Do that once the first benefits task exists, since that's when they'll get real use.
