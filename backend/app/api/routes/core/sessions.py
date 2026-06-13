from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import SessionServiceDep
from app.features.core.sessions.schemas import SessionCreate, SessionFilters, SessionRead

router = APIRouter(prefix="/core/sessions", tags=["core"], dependencies=[Depends(require_auth)])


@router.get("/", response_model=list[SessionRead])
async def list_sessions(service: SessionServiceDep, filters: SessionFilters = Depends()):
    return await service.list(filters)


@router.get("/{session_id}", response_model=SessionRead)
async def get_session(session_id: int, service: SessionServiceDep):
    obj = await service.get(session_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return obj


@router.post("/", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(data: SessionCreate, service: SessionServiceDep):
    return await service.create(data)


@router.post("/{session_id}/finish", response_model=SessionRead)
async def finish_session(session_id: int, service: SessionServiceDep):
    obj = await service.finish(session_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return obj


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: int, service: SessionServiceDep):
    deleted = await service.delete(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
