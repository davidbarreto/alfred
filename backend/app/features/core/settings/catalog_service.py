import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.settings.catalog import build_catalog
from app.features.core.settings.catalog_schemas import SettingsCatalogRead
from app.features.core.settings.service import SettingService

logger = logging.getLogger(__name__)


class SettingsCatalogService:
    """Read-only: the settings catalog plus the stored keys no field covers."""

    def __init__(self, session: AsyncSession) -> None:
        self._settings = SettingService(session)

    async def get(self) -> SettingsCatalogRead:
        catalog = build_catalog(await self._settings.list_values(""))
        logger.debug(
            "Settings catalog built: namespaces=%d unregistered=%d", len(catalog.namespaces), len(catalog.unregistered)
        )
        return catalog
