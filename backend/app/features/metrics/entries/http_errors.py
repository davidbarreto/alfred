from fastapi import HTTPException, status

from app.features.metrics.entries.service import (
    MetricAmbiguousStopError,
    MetricInvalidEntryError,
    MetricKindMismatchError,
    MetricNothingRunningError,
    MetricSeriesArchivedError,
    MetricSeriesNotFoundError,
    MetricStaleEntryError,
)

_CONFLICTS = (
    MetricKindMismatchError,
    MetricNothingRunningError,
    MetricAmbiguousStopError,
    MetricStaleEntryError,
    MetricSeriesArchivedError,
)


def to_http_error(exc: Exception) -> HTTPException:
    """Map the metric entry service's domain errors onto HTTP status codes."""
    if isinstance(exc, MetricSeriesNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Series {exc} not found")
    if isinstance(exc, _CONFLICTS):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, MetricInvalidEntryError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    raise exc


ENTRY_ERRORS = (*_CONFLICTS, MetricInvalidEntryError, MetricSeriesNotFoundError)
