from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.dependencies.error_codes import ErrorCode
from app.api.schemas.product_import import ProductImportResponse
from app.services.product_import_service import (
    ProductImportError,
    import_products_from_excel_service,
)

router = APIRouter()


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, ProductImportError):
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.error_code,
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=ErrorCode.INTERNAL_SERVER_ERROR,
    ) from exc


@router.post(
    "/import",
    response_model=ProductImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_products(file: UploadFile = File(...)) -> ProductImportResponse:
    try:
        return await import_products_from_excel_service(upload=file)
    except Exception as exc:
        _raise_http_error(exc)
