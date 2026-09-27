---
name: env-idea-scorecard
description: Score a candidate RL environment idea against ttune's criteria (verifiability, compute, saturation, realism, generatability, hack-resistance, real-world impact) and record the verdict in the docs. Use whenever the user floats a new environment or domain idea, asks "is X a good env?", wants to compare env ideas, or asks what to build next — even if they don't say "score" or "scorecard".
---

# Environment idea scorecard

ttune builds Harbor-format RL environments on little compute. Most env ideas fail on one of a few predictable axes, so score every new idea the same way before anyone builds it. The point is a fast, honest go/no-go, not a sales pitch for the idea.

## Context to load first

Read these so the score reflects decisions already made, not first principles:

- `docs/02-realistic-environments.md`: existing candidate ideas (avoid duplicates; compare against them)
- `docs/03-trends-2026.md`: what's saturated vs underserved
- `docs/04-benefits-eligibility-plan.md`: the current main direction

## Criteria

Score each 1–5 with one line of evidence. The evidence matters more than the number.

| Criterion | 5 looks like | 1 looks like |
|---|---|---|
| **Verifiability** | An existing deterministic engine computes the answer (tax engine, PolicyEngine, KiCad DRC, OR-Tools, a simulator) | Only an LLM judge can tell good from bad |
| **Compute** | CPU-only container, verifier runs in seconds | Needs GPUs, a heavy simulator, or long-running services |
| **Saturation** | No public benchmark or Harbor dataset covers it | Terminal-Bench / SWE-style tasks already cover it |
| **Realism** | Inputs are messy real-world artifacts (scans, contradictions, missing docs) | Clean toy inputs |
| **Generatability** | One generator yields thousands of distinct, graded tasks | Every task is hand-written |
| **Hack-resistance** | Ground truth can live outside the agent's container; outcome, not format, is checked | Answer is inferable from the inputs' structure or the verifier checks format only |
| **Impact** | A skill that matters to real people or a real industry | Puzzle with no transfer |

To check saturation, fetch Harbor's registry and search it for the domain's keywords:

```bash
curl -sL https://raw.githubusercontent.com/laude-institute/harbor/main/registry.json -o /tmp/harbor-registry.json
grep -io '"name": *"[^"]*' /tmp/harbor-registry.json | grep -i '<keyword>'
```

If network access fails, say saturation is unchecked rather than guessing.

## Verdict rules

- Verifiability ≤ 2 → **no-go** unless the user explicitly wants a judge-graded env; judge-only rewards are the easiest to hack.
- Compute ≤ 2 → **no-go** for ttune (the project constraint is little compute).
- Otherwise: **go** if total ≥ 26/35, **maybe** if 20–25, **no-go** below 20.

## Output

Reply with this structure, then offer to append it to `docs/02-realistic-environments.md` under a `## Scored ideas` section (create it if missing):

```markdown
### <Idea name>
**Task:** one sentence. **Verifier:** one sentence.

| Criterion | Score | Evidence |
|---|---|---|
| Verifiability | 4 | ... |
| ... | | |
| **Total** | **27/35** | |

**Verdict:** go / maybe / no-go. **Biggest risk:** one sentence. **Cheapest first task:** one sentence.
```

Keep it short. If the idea is a near-duplicate of an existing one in docs/02, say which and score only the difference.
