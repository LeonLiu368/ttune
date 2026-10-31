from pathlib import Path

from rewardkit import criterion

from task_score import dimension


@criterion(description="amount: see /opt/ttune/verify.py")
def amount(workspace: Path) -> float:
    return dimension(workspace, "amount")
