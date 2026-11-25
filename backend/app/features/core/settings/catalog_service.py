import logging

from app.features.core.settings.catalog import build_catalog
from app.features.core.settings.catalog_schemas import SettingsCatalogRead

logger = logging.getLogger(__name__)


class SettingsCatalogService:
    """Read-only: the settings catalog. It holds no values; each namespace's own GET does."""

    async def get(self) -> SettingsCatalogRead:
        catalog = build_catalog()
        logger.debug("Settings catalog built: namespaces=%d", len(catalog.namespaces))
        return catalog
