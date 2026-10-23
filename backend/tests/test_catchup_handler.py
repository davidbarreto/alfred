from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.catchup import handle_catchup
from app.features.core.catchup.schemas import (
    CatchupApply,
    CatchupApplyRead,
    CatchupMove,
    CatchupRead,
    CatchupSuggestion,
    CatchupTask,
)


@pytest.fixture
def mock_service():
    return AsyncMock()


def _task(id=1, title="Pay invoice", days_overdue=4):
    return CatchupTask(id=id, title=title, priority="HIGH", urgency="URGENT", days_overdue=days_overdue)


def _read():
    return CatchupRead(
        today_top=[_task()],
        suggestions=[
            CatchupSuggestion(
                kind="spread", title="Spread 2 overdue tasks over the next days", detail="At most 3 due per day.",
                moves=[
                    CatchupMove(
                        task_id=5, title="Call plumber", priority="MEDIUM",
                        old_deadline=datetime(2026, 10, 1, 9, 0), new_deadline=datetime(2026, 10, 24, 9, 0),
                    )
                ],
                command="/catchupapply spread",
            ),
            CatchupSuggestion(
                kind="drop", title="Drop 1 stale task(s)?", detail="Cancels them.",
                tasks=[_task(id=7, title="Old idea", days_overdue=50)], command="/catchupapply drop 7",
            ),
        ],
    )


class TestShow:
    async def test_returns_structured_data_and_a_readable_text(self, mock_service):
        mock_service.get_suggestions.return_value = _read()

        result = await handle_catchup("show", {}, mock_service)

        assert result["today_top"][0]["id"] == 1
        text = result["text"]
        assert "Focus today:" in text
        assert "- #1 Pay invoice (HIGH, overdue 4d)" in text
        assert "1) Spread 2 overdue tasks over the next days" in text
        assert "- #5 Call plumber -> Sat 24 Oct" in text
        assert "Apply: /catchupapply spread" in text
        assert "2) Drop 1 stale task(s)?" in text
        assert "- #7 Old idea (HIGH, overdue 50d)" in text
        assert "Apply: /catchupapply drop 7" in text

    async def test_nothing_to_do_message(self, mock_service):
        mock_service.get_suggestions.return_value = CatchupRead(today_top=[], suggestions=[])

        result = await handle_catchup("show", {}, mock_service)

        assert result["text"] == "Nothing to catch up on: no overdue or urgent tasks."

    async def test_long_lists_are_truncated(self, mock_service):
        moves = [
            CatchupMove(
                task_id=i, title=f"T{i}", priority="LOW",
                old_deadline=datetime(2026, 10, 1), new_deadline=datetime(2026, 10, 24),
            )
            for i in range(11)
        ]
        mock_service.get_suggestions.return_value = CatchupRead(
            today_top=[], suggestions=[CatchupSuggestion(kind="spread", title="t", detail="d", moves=moves)]
        )

        result = await handle_catchup("show", {}, mock_service)

        assert "+3 more" in result["text"]


class TestApply:
    async def test_spread(self, mock_service):
        mock_service.apply.return_value = CatchupApplyRead(kind="spread", applied=4, skipped=0)

        result = await handle_catchup("apply", {"kind": "Spread"}, mock_service)

        mock_service.apply.assert_awaited_once_with(CatchupApply(kind="spread", task_ids=None))
        assert result == {"kind": "spread", "applied": 4, "skipped": 0}

    async def test_drop_parses_the_id_list(self, mock_service):
        mock_service.apply.return_value = CatchupApplyRead(kind="drop", applied=2, skipped=0)

        await handle_catchup("apply", {"kind": "drop", "ids": "12, 15"}, mock_service)

        mock_service.apply.assert_awaited_once_with(CatchupApply(kind="drop", task_ids=[12, 15]))

    async def test_drop_requires_ids(self, mock_service):
        with pytest.raises(HTTPException) as exc:
            await handle_catchup("apply", {"kind": "drop"}, mock_service)

        assert exc.value.status_code == 400
        mock_service.apply.assert_not_awaited()

    async def test_unknown_kind_is_a_usage_error(self, mock_service):
        with pytest.raises(HTTPException) as exc:
            await handle_catchup("apply", {"kind": "nuke"}, mock_service)

        assert exc.value.status_code == 400
        assert "Usage" in exc.value.detail

    async def test_non_numeric_ids_are_rejected(self, mock_service):
        with pytest.raises(HTTPException) as exc:
            await handle_catchup("apply", {"kind": "drop", "ids": "12,abc"}, mock_service)

        assert exc.value.status_code == 400


class TestUnknownCommand:
    async def test_raises_400(self, mock_service):
        with pytest.raises(HTTPException) as exc:
            await handle_catchup("explode", {}, mock_service)

        assert exc.value.status_code == 400
