from pathlib import Path

from rewardkit import criterion

from task_score import dimension


@criterion(description="eligibility: see /opt/ttune/verify.py")
def eligibility(workspace: Path) -> float:
    return dimension(workspace, "eligibility")
