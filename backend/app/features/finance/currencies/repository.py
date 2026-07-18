from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.currencies.tables import Currency
from app.features.finance.currencies.schemas import CurrencyCreate, CurrencyUpdate


class CurrencyRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, code: str) -> Currency | None:
        result = await self._session.execute(select(Currency).where(Currency.code == code))
        return result.scalars().first()

    async def list(self) -> list[Currency]:
        result = await self._session.execute(select(Currency).order_by(Currency.code))
        return list(result.scalars().all())

    async def create(self, data: CurrencyCreate) -> Currency:
        currency = Currency(**data.model_dump())
        self._session.add(currency)
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            raise
        await self._session.refresh(currency)
        return currency

    async def update(self, code: str, data: CurrencyUpdate) -> Currency | None:
        currency = await self.get(code)
        if currency is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(currency, field, value)
        await self._session.commit()
        await self._session.refresh(currency)
        return currency

    async def delete(self, code: str) -> bool:
        currency = await self.get(code)
        if currency is None:
            return False
        await self._session.delete(currency)
        await self._session.commit()
        return True
