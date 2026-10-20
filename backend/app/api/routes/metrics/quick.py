from fastapi import APIRouter, Depends, Request

from app.api.auth import require_auth
from app.features.metrics.entries.http_errors import ENTRY_ERRORS, to_http_error
from app.dependencies import MetricEntryServiceDep
from app.features.metrics.entries.schemas import MetricActionResult, MetricLog, MetricStart, MetricStop

router = APIRouter(
    prefix="/metrics/quick",
    tags=["metrics"],
    dependencies=[Depends(require_auth)],
)

_SOURCE_BY_CLIENT = {"shortcut": "shortcut", "web": "portal"}


def _source(request: Request) -> str:
    return _SOURCE_BY_CLIENT.get(request.headers.get("x-alfred-client", ""), "mcp")


@router.post("/start", response_model=MetricActionResult)
async def quick_start(request: Request, body: MetricStart, service: MetricEntryServiceDep) -> MetricActionResult:
    try:
        return await service.start(body, _source(request))
    except ENTRY_ERRORS as exc:
        raise to_http_error(exc)


@router.post("/stop", response_model=MetricActionResult)
async def quick_stop(request: Request, body: MetricStop, service: MetricEntryServiceDep) -> MetricActionResult:
    try:
        return await service.stop(body, _source(request))
    except ENTRY_ERRORS as exc:
        raise to_http_error(exc)


@router.post("/log", response_model=MetricActionResult)
async def quick_log(request: Request, body: MetricLog, service: MetricEntryServiceDep) -> MetricActionResult:
    try:
        return await service.log(body, _source(request))
    except ENTRY_ERRORS as exc:
        raise to_http_error(exc)
