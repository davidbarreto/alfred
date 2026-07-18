import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.currencies.repository import CurrencyRepository
from app.features.finance.currencies.schemas import (
    CurrencyCreate,
    CurrencyRead,
    CurrencyUpdate,
)

logger = logging.getLogger(__name__)


class DuplicateCurrencyError(Exception):
    """Raised when creating a currency whose code already exists (code is the primary key)."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Currency {code} already exists")


class CurrencyService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = CurrencyRepository(session)

    async def get(self, code: str) -> CurrencyRead | None:
        currency = await self._repo.get(code.strip().upper())
        if currency is None:
            return None
        return CurrencyRead.model_validate(currency)

    async def list(self) -> list[CurrencyRead]:
        currencies = await self._repo.list()
        return [CurrencyRead.model_validate(c) for c in currencies]

    async def create(self, data: CurrencyCreate) -> CurrencyRead:
        try:
            currency = await self._repo.create(data)
        except IntegrityError:
            logger.warning("Currency create blocked: code=%s already exists", data.code)
            raise DuplicateCurrencyError(data.code)
        logger.info("Currency created: code=%s name=%r", currency.code, data.name)
        return CurrencyRead.model_validate(currency)

    async def update(self, code: str, data: CurrencyUpdate) -> CurrencyRead | None:
        currency = await self._repo.update(code.strip().upper(), data)
        if currency is None:
            logger.debug("Currency update: code=%s not found", code)
            return None
        logger.info(
            "Currency updated: code=%s fields=%s", code, list(data.model_dump(exclude_unset=True).keys())
        )
        return CurrencyRead.model_validate(currency)

    async def delete(self, code: str) -> bool:
        deleted = await self._repo.delete(code.strip().upper())
        if deleted:
            logger.info("Currency deleted: code=%s", code)
        else:
            logger.debug("Currency delete: code=%s not found", code)
        return deleted
