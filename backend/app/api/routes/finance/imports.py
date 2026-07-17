from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status

from app.api.auth import require_auth
from app.dependencies import ImportServiceDep
from app.features.finance.imports.schemas import (
    ImportBatchRead,
    ImportCommitRequest,
    ImportCommitResponse,
    ImportPreviewResponse,
    ImportRuleCreate,
    ImportRuleRead,
)

router = APIRouter(prefix="/finance/imports", tags=["finance"], dependencies=[Depends(require_auth)])


@router.get("/providers", response_model=list[str])
async def list_providers(service: ImportServiceDep):
    return service.available_providers()


@router.post("/preview", response_model=ImportPreviewResponse)
async def preview_import(
    service: ImportServiceDep,
    file: UploadFile = File(...),
    account_id: int = Form(...),
    provider: str | None = Form(None),
):
    content = await file.read()
    result = await service.preview(
        account_id=account_id,
        filename=file.filename or "statement",
        content=content,
        provider=provider,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No parser available for this file",
        )
    return result


@router.post("/commit", response_model=ImportCommitResponse, status_code=status.HTTP_201_CREATED)
async def commit_import(request: ImportCommitRequest, service: ImportServiceDep):
    return await service.commit(request)


@router.get("/rules", response_model=list[ImportRuleRead])
async def list_rules(service: ImportServiceDep):
    return await service.list_rules()


@router.post("/rules", response_model=ImportRuleRead, status_code=status.HTTP_201_CREATED)
async def create_rule(request: ImportRuleCreate, service: ImportServiceDep):
    return await service.create_rule(request)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: int, service: ImportServiceDep):
    deleted = await service.delete_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", response_model=list[ImportBatchRead])
async def list_batches(service: ImportServiceDep):
    return await service.list_batches()


@router.get("/{batch_id}/file")
async def download_batch_file(batch_id: int, service: ImportServiceDep):
    stored = await service.get_batch_file(batch_id)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No stored file for this batch")
    content, filename = stored
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_batch(batch_id: int, service: ImportServiceDep):
    deleted = await service.delete_batch(batch_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import batch not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
