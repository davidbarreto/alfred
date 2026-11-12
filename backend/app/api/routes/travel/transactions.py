from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import TransactionLinkServiceDep, TripDefaultTagServiceDep
from app.features.travel.errors import TravelNotFoundError
from app.features.travel.transaction_links.schemas import (
    ApplyDefaultTagsResult,
    LinkedTransaction,
    LinkedTransactions,
    LinkKind,
    PlaceCosts,
    TransactionLinkCreate,
    TripCosts,
)
from app.features.travel.transaction_links.service import TransferNotLinkableError

router = APIRouter(prefix="/travel", tags=["travel"], dependencies=[Depends(require_auth)])


@router.get("/trips/{trip_id}/costs", response_model=TripCosts)
async def get_trip_costs(trip_id: int, service: TransactionLinkServiceDep) -> TripCosts:
    costs = await service.get_trip_costs(trip_id)
    if costs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return costs


@router.get("/trips/{trip_id}/unlinked-transactions", response_model=list[LinkedTransaction])
async def get_unlinked_transactions(trip_id: int, service: TransactionLinkServiceDep) -> list[LinkedTransaction]:
    """Expenses dated within the trip (or tagged with its default tags) and tagged income not linked to any leg, stay or visit."""
    found = await service.get_unlinked(trip_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return found


@router.post("/trips/{trip_id}/apply-default-tags", response_model=ApplyDefaultTagsResult)
async def apply_default_tags(trip_id: int, service: TripDefaultTagServiceDep) -> ApplyDefaultTagsResult:
    try:
        names, added = await service.apply_to_existing(trip_id)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return ApplyDefaultTagsResult(tags=names, added=added)


@router.get("/places/{place_id}/costs", response_model=PlaceCosts)
async def get_place_costs(place_id: int, service: TransactionLinkServiceDep) -> PlaceCosts:
    costs = await service.get_place_costs(place_id)
    if costs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Place not found")
    return costs


@router.get("/{kind}/{entity_id}/transactions", response_model=LinkedTransactions)
async def get_linked_transactions(kind: LinkKind, entity_id: int, service: TransactionLinkServiceDep) -> LinkedTransactions:
    try:
        return await service.get_linked(kind, entity_id)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/{kind}/{entity_id}/transactions", response_model=LinkedTransactions)
async def link_transaction(
    kind: LinkKind, entity_id: int, request: TransactionLinkCreate, service: TransactionLinkServiceDep
) -> LinkedTransactions:
    try:
        return await service.link(kind, entity_id, request.transaction_id)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except TransferNotLinkableError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.delete("/{kind}/{entity_id}/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_transaction(
    kind: LinkKind, entity_id: int, transaction_id: int, service: TransactionLinkServiceDep
) -> Response:
    try:
        removed = await service.unlink(kind, entity_id, transaction_id)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction is not linked")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
