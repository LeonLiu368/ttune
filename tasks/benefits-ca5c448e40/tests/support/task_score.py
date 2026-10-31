"""Shared by the three criteria: score /app/answer.json once against the baked-in truth."""

import os
from functools import cache
from pathlib import Path

from verify import evaluate, load


@cache
def _scores(workspace: str) -> dict:
    path = Path(workspace) / "answer.json"
    text = path.read_text() if path.is_file() else None
    try:
        return evaluate(text, load(os.environ.get("TTUNE_TRUTH", "/opt/ttune/truth.json")))
    except Exception as exc:  # a crash in grading scores 0, never passes
        return {"eligibility": 0.0, "amount": 0.0, "missing_info": 0.0, "error": repr(exc)}


def dimension(workspace: Path, name: str) -> float:
    return float(_scores(str(workspace))[name])
