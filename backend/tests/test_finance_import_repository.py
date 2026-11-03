from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.imports.repository import ImportRepository
from app.features.finance.imports.tables import ImportBatch


class TestGetLatestClosingBalanceBatch:
    @pytest.mark.asyncio
    async def test_returns_the_first_row_of_the_ordered_query(self):
        session = AsyncMock(spec=AsyncSession)
        batch = ImportBatch(closing_balance=Decimal("-10.00"))
        result = MagicMock()
        result.scalars.return_value.first.return_value = batch
        session.execute.return_value = result

        found = await ImportRepository(session).get_latest_closing_balance_batch(5)

        assert found is batch

    @pytest.mark.asyncio
    async def test_query_requires_a_closing_balance_and_period_end_and_sorts_newest_period_first(self):
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        result.scalars.return_value.first.return_value = None
        session.execute.return_value = result

        await ImportRepository(session).get_latest_closing_balance_batch(5)

        sql = str(session.execute.await_args.args[0].compile(dialect=postgresql.dialect()))
        assert "closing_balance IS NOT NULL" in sql
        assert "period_end IS NOT NULL" in sql
        assert "ORDER BY finance.import_batches.period_end DESC, finance.import_batches.id DESC" in sql
