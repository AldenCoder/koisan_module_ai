from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.schemas.dashboard_report import (
    DashboardReportPageIdsResponse,
    DashboardReportResponse,
)
from app.core.security import CurrentUser, require_permission
from app.services.dashboard_report_service import (
    EXCEL_CONTENT_TYPE,
    export_dashboard_report_excel_service,
    get_dashboard_report_service,
    list_dashboard_report_page_ids_service,
)
from logs.logging_config import logger


router = APIRouter()


@router.get("/report", response_model=DashboardReportResponse)
async def get_dashboard_report(
    from_date: str = Query(..., description="Report start date, YYYY-MM-DD or ISO datetime"),
    to_date: str = Query(..., description="Report end date, YYYY-MM-DD or ISO datetime"),
    page_id: Optional[str] = Query(default=None),
    thread_type: Optional[str] = Query(default=None, description="inbox or comment"),
    role: Optional[str] = Query(default=None, description="user, staff, bot, or system"),
    include_inactive: bool = Query(default=False),
    alert_limit: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_permission("conversations:view")),
) -> DashboardReportResponse:
    del current_user
    try:
        result = await get_dashboard_report_service(
            from_date=from_date,
            to_date=to_date,
            page_id=page_id,
            thread_type=thread_type,
            role=role,
            include_inactive=include_inactive,
            alert_limit=alert_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return DashboardReportResponse(**result)


@router.get("/report/export")
async def export_dashboard_report(
    from_date: str = Query(..., description="Report start date, YYYY-MM-DD or ISO datetime"),
    to_date: str = Query(..., description="Report end date, YYYY-MM-DD or ISO datetime"),
    page_id: Optional[str] = Query(default=None),
    thread_type: Optional[str] = Query(default=None, description="inbox or comment"),
    role: Optional[str] = Query(default=None, description="user, staff, bot, or system"),
    include_inactive: bool = Query(default=False),
    alert_limit: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_permission("conversations:view")),
) -> Response:
    del current_user
    try:
        content, filename = await export_dashboard_report_excel_service(
            from_date=from_date,
            to_date=to_date,
            page_id=page_id,
            thread_type=thread_type,
            role=role,
            include_inactive=include_inactive,
            alert_limit=alert_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("DASHBOARD_REPORT_EXPORT_FAILED")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="dashboard_report_export_failed",
        ) from exc

    return Response(
        content=content,
        media_type=EXCEL_CONTENT_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/report/page-ids", response_model=DashboardReportPageIdsResponse)
async def list_dashboard_report_page_ids(
    include_inactive: bool = Query(default=False),
    current_user: CurrentUser = Depends(require_permission("conversations:view")),
) -> DashboardReportPageIdsResponse:
    del current_user
    result = await list_dashboard_report_page_ids_service(
        include_inactive=include_inactive,
    )
    return DashboardReportPageIdsResponse(**result)
