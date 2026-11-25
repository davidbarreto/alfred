from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import SettingsCatalogServiceDep
from app.features.core.settings.catalog_schemas import SettingsCatalogRead

router = APIRouter(prefix="/core/settings", tags=["core"], dependencies=[Depends(require_auth)])


@router.get("/catalog", response_model=SettingsCatalogRead)
async def get_settings_catalog(service: SettingsCatalogServiceDep) -> SettingsCatalogRead:
    return await service.get()
