import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status

from app.api.auth import require_auth
from app.dependencies import ImportServiceDep
from app.features.finance.imports.schemas import (
    DetectCurrenciesResponse,
    ImportBatchRead,
    ImportCommitGroupedRequest,
    ImportCommitGroupedResponse,
    ImportCommitRequest,
    ImportCommitResponse,
    ImportPreviewGroupedResponse,
    ImportPreviewResponse,
    ImportRuleCreate,
    ImportRuleFilters,
    ImportRuleRead,
    ImportRuleReorderRequest,
    ImportRuleUpdate,
)
from app.features.finance.imports.service import InvalidGroupedImportError

router = APIRouter(prefix="/finance/imports", tags=["finance"], dependencies=[Depends(require_auth)])


@router.get("/providers", response_model=list[str])
async def list_providers(service: ImportServiceDep):
    return service.available_providers()


@router.get("/providers-grouped", response_model=list[str])
async def list_grouped_providers(service: ImportServiceDep):
    return service.available_grouped_providers()


@router.post("/detect-currencies", response_model=DetectCurrenciesResponse)
async def detect_currencies(
    service: ImportServiceDep,
    file: UploadFile = File(...),
    provider: str = Form(...),
):
    content = await file.read()
    result = await service.detect_currencies(
        filename=file.filename or "statement", content=content, provider=provider
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No parser available for this file",
        )
    return result


@router.post("/preview-grouped", response_model=ImportPreviewGroupedResponse)
async def preview_import_grouped(
    service: ImportServiceDep,
    file: UploadFile = File(...),
    provider: str = Form(...),
    account_map: str = Form(...),
):
    try:
        parsed_map = {k: int(v) for k, v in json.loads(account_map).items()}
    except (json.JSONDecodeError, ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid account_map")

    content = await file.read()
    try:
        result = await service.preview_grouped(
            account_map=parsed_map,
            filename=file.filename or "statement",
            content=content,
            provider=provider,
        )
    except InvalidGroupedImportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No parser available for this file",
        )
    return result


@router.post(
    "/commit-grouped", response_model=ImportCommitGroupedResponse, status_code=status.HTTP_201_CREATED
)
async def commit_import_grouped(request: ImportCommitGroupedRequest, service: ImportServiceDep):
    try:
        return await service.commit_grouped(request)
    except InvalidGroupedImportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)


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
async def list_rules(service: ImportServiceDep, filters: ImportRuleFilters = Depends()):
    return await service.list_rules_page(filters)


@router.post("/rules", response_model=ImportRuleRead, status_code=status.HTTP_201_CREATED)
async def create_rule(request: ImportRuleCreate, service: ImportServiceDep):
    return await service.create_rule(request)


@router.post("/rules/reorder", response_model=list[ImportRuleRead])
async def reorder_rules(request: ImportRuleReorderRequest, service: ImportServiceDep):
    return await service.reorder_rules(request.rule_ids)


@router.patch("/rules/{rule_id}", response_model=ImportRuleRead)
async def update_rule(rule_id: int, request: ImportRuleUpdate, service: ImportServiceDep):
    rule = await service.update_rule(rule_id, request)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return rule


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
