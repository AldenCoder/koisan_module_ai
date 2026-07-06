from fastapi import (
    APIRouter,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from app.api.dependencies.error_codes import ErrorCode
from app.api.schemas.image_search import (
    CropAwareImageSearchResponse,
    PublicImageCropSearchRequest,
    PublicImageCropSearchResponse,
)
from app.services.chroma_crop_aware_index import (
    search_chroma_crop_aware_image_service,
)
from app.services.foreground_common import CropAwareImageSearchError
from app.services.public_image_crop_search_service import (
    search_public_image_crop_service,
)

router = APIRouter()


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, CropAwareImageSearchError):
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.error_code,
        ) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ErrorCode.INVALID_INPUT_DATA,
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=ErrorCode.INTERNAL_SERVER_ERROR,
    ) from exc


@router.post("/crop-aware", response_model=CropAwareImageSearchResponse)
async def search_crop_aware_image(
    file: UploadFile = File(...),
    top_k: int = Query(default=10, ge=1, le=100),
    aggregate_k: int = Query(default=1, ge=1, le=20),
) -> CropAwareImageSearchResponse:
    try:
        return await search_chroma_crop_aware_image_service(
            upload=file,
            top_k=top_k,
            aggregate_k=aggregate_k,
        )
    except Exception as exc:
        _raise_http_error(exc)


@router.post(
    "/public-crop",
    response_model=PublicImageCropSearchResponse,
)
async def search_public_image_crop(
    payload: PublicImageCropSearchRequest,
) -> PublicImageCropSearchResponse:
    return await search_public_image_crop_service(payload)
