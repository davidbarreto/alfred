from datetime import datetime
from typing import Any

_PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def task_priority_sort_key(task: Any, now: datetime) -> tuple:
    """Priority first, then overdue, then earliest deadline.

    Shared by /focus and the evening digest so both rank tasks the same way
    a HIGH undated task shouldn't sink below a LOW dated one.
    """
    is_overdue = task.deadline is not None and task.deadline < now
    return (
        _PRIORITY_ORDER.get(task.priority, len(_PRIORITY_ORDER)),
        0 if is_overdue else 1,
        task.deadline or datetime.max,
    )
