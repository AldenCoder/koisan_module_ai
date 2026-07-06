import json
from json import JSONDecodeError
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from pydantic import ValidationError

from app.api.dependencies.error_codes import ErrorCode
from app.api.schemas.image_asset import normalize_remove_image_file_names
from app.api.schemas.image_search_source import (
    ImageSearchSourceDeleteResponse,
    ImageSearchSourceDetailResponse,
    ImageSearchSourceImportResponse,
    ImageSearchSourceListResponse,
    ImageSearchSourceUpdateResponse,
)
from app.core.security import CurrentUser, require_permission
from app.services.foreground_common import CropAwareImageSearchError
from app.services.image_search_source_service import (
    delete_image_search_source_service,
    get_image_search_source_service,
    import_image_search_sources_service,
    list_image_search_sources_service,
    update_image_search_source_service,
)

router = APIRouter()


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, CropAwareImageSearchError):
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.error_code,
        ) from exc
    if isinstance(exc, (ValidationError, ValueError)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ErrorCode.INVALID_INPUT_DATA,
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=ErrorCode.INTERNAL_SERVER_ERROR,
    ) from exc


def _parse_delete_file_names(value: Optional[str]) -> Optional[List[str]]:
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ErrorCode.INVALID_INPUT_DATA,
        ) from exc
    if not isinstance(parsed, list) or not all(
        isinstance(item, str) for item in parsed
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ErrorCode.INVALID_INPUT_DATA,
        )
    try:
        return normalize_remove_image_file_names(parsed)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ErrorCode.INVALID_INPUT_DATA,
        ) from exc


@router.get("", response_model=ImageSearchSourceListResponse)
async def list_image_search_sources(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    keyword: Optional[str] = Query(default=None, max_length=100),
    current_user: CurrentUser = Depends(require_permission("image_assets:view")),
) -> ImageSearchSourceListResponse:
    del current_user
    try:
        return list_image_search_sources_service(
            page=page,
            size=size,
            keyword=keyword,
        )
    except Exception as exc:
        _raise_http_error(exc)


@router.post(
    "",
    response_model=ImageSearchSourceImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_image_search_sources(
    code: str = Form(..., max_length=100),
    description: Optional[str] = Form(default=None, max_length=5000),
    files: List[UploadFile] = File(...),
    current_user: CurrentUser = Depends(require_permission("image_assets:create")),
) -> ImageSearchSourceImportResponse:
    del current_user
    try:
        return await import_image_search_sources_service(
            code=code,
            description=description,
            uploads=files,
        )
    except Exception as exc:
        _raise_http_error(exc)


@router.get("/{code}", response_model=ImageSearchSourceDetailResponse)
async def get_image_search_source(
    code: str,
    current_user: CurrentUser = Depends(require_permission("image_assets:view")),
) -> ImageSearchSourceDetailResponse:
    del current_user
    try:
        return get_image_search_source_service(code=code)
    except Exception as exc:
        _raise_http_error(exc)


@router.patch("/{code}", response_model=ImageSearchSourceUpdateResponse)
async def update_image_search_source(
    code: str,
    request: Request,
    description: Optional[str] = Form(default=None, max_length=5000),
    add_files: Optional[List[UploadFile]] = File(default=None),
    delete_file_names: Optional[str] = Form(default=None),
    current_user: CurrentUser = Depends(require_permission("image_assets:edit")),
) -> ImageSearchSourceUpdateResponse:
    del current_user
    try:
        form = await request.form()
        return await update_image_search_source_service(
            code=code,
            description=description,
            description_provided="description" in form,
            add_uploads=add_files,
            delete_file_names=_parse_delete_file_names(delete_file_names),
        )
    except HTTPException:
        raise
    except Exception as exc:
        _raise_http_error(exc)


@router.delete("/{code}", response_model=ImageSearchSourceDeleteResponse)
async def delete_image_search_source(
    code: str,
    current_user: CurrentUser = Depends(require_permission("image_assets:delete")),
) -> ImageSearchSourceDeleteResponse:
    del current_user
    try:
        return await delete_image_search_source_service(code=code)
    except Exception as exc:
        _raise_http_error(exc)
