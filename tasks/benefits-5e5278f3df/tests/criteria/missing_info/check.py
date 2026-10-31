from pathlib import Path

from rewardkit import criterion

from task_score import dimension


@criterion(description="missing_info: see /opt/ttune/verify.py")
def missing_info(workspace: Path) -> float:
    return dimension(workspace, "missing_info")
