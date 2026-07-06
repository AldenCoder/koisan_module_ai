import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.dependencies.time import VN_TZ
from app.core.security import get_current_user
from app.api.v1 import dashboard_reports as api
from app.services.dashboard_report_service import EXCEL_CONTENT_TYPE


def _report_payload():
    now = datetime(2026, 6, 26, 10, 0, tzinfo=VN_TZ)
    return {
        "filters": {
            "from_date": now,
            "to_date": now,
            "page_id": None,
            "thread_type": None,
            "role": None,
            "include_inactive": False,
            "alert_limit": 20,
        },
        "summary": {
            "total_messages": 0,
            "text_messages": 0,
            "image_messages": 0,
            "user_messages": 0,
            "staff_messages": 0,
            "bot_messages": 0,
            "total_conversations": 0,
            "new_conversations": 0,
            "confirmed_conversations": 0,
            "handover_conversations": 0,
            "apilimit_conversations": 0,
            "order_pending_conversations": 0,
            "needs_support_count": 0,
            "order_alert_count": 0,
        },
        "messages_by_day": [],
        "conversation_status": [],
        "alerts": {"needs_support": [], "orders": []},
    }


def test_get_dashboard_report_api_returns_response(monkeypatch):
    service_mock = AsyncMock(return_value=_report_payload())
    monkeypatch.setattr(api, "get_dashboard_report_service", service_mock)

    result = asyncio.run(
        api.get_dashboard_report(
            from_date="2026-06-01",
            to_date="2026-06-26",
            page_id="page-1",
            thread_type="inbox",
            role="user",
            include_inactive=False,
            alert_limit=20,
        )
    )

    assert result.summary.total_messages == 0
    service_mock.assert_awaited_once_with(
        from_date="2026-06-01",
        to_date="2026-06-26",
        page_id="page-1",
        thread_type="inbox",
        role="user",
        include_inactive=False,
        alert_limit=20,
    )


def test_get_dashboard_report_api_maps_value_error_to_400(monkeypatch):
    monkeypatch.setattr(
        api,
        "get_dashboard_report_service",
        AsyncMock(side_effect=ValueError("from_date_must_be_before_to_date")),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            api.get_dashboard_report(
                from_date="2026-06-26",
                to_date="2026-06-01",
                page_id=None,
                thread_type=None,
                role=None,
                include_inactive=False,
                alert_limit=20,
            )
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "from_date_must_be_before_to_date"


def _current_user():
    return SimpleNamespace(
        email="admin@example.com",
        quyen_han=[SimpleNamespace(ten="conversations:view")],
    )


def _client():
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1/dashboard")
    app.dependency_overrides[get_current_user] = _current_user
    return TestClient(app)


@pytest.mark.parametrize(
    "url",
    [
        "/api/v1/dashboard/report?to_date=2026-06-26",
        "/api/v1/dashboard/report?from_date=2026-06-26",
    ],
)
def test_get_dashboard_report_api_requires_date_filters(url):
    response = _client().get(url)

    assert response.status_code == 422


def test_list_dashboard_report_page_ids_api_returns_response(monkeypatch):
    service_mock = AsyncMock(
        return_value={
            "items": [
                {
                    "page_id": "page-1",
                    "conversation_count": 2,
                    "message_count": 7,
                    "latest_activity_at": datetime(2026, 6, 26, 10, 0, tzinfo=VN_TZ),
                }
            ]
        }
    )
    monkeypatch.setattr(api, "list_dashboard_report_page_ids_service", service_mock)

    result = asyncio.run(
        api.list_dashboard_report_page_ids(include_inactive=True)
    )

    assert result.items[0].page_id == "page-1"
    assert result.items[0].conversation_count == 2
    assert result.items[0].message_count == 7
    service_mock.assert_awaited_once_with(include_inactive=True)


def test_export_dashboard_report_api_returns_xlsx_response(monkeypatch):
    export_mock = AsyncMock(return_value=(b"xlsx-bytes", "dashboard-report.xlsx"))
    monkeypatch.setattr(api, "export_dashboard_report_excel_service", export_mock)

    result = asyncio.run(
        api.export_dashboard_report(
            from_date="2026-06-01",
            to_date="2026-06-26",
            page_id="page-1",
            thread_type="inbox",
            role=None,
            include_inactive=False,
            alert_limit=20,
        )
    )

    assert result.media_type == EXCEL_CONTENT_TYPE
    assert result.body == b"xlsx-bytes"
    assert result.headers["content-disposition"] == (
        'attachment; filename="dashboard-report.xlsx"'
    )
    export_mock.assert_awaited_once_with(
        from_date="2026-06-01",
        to_date="2026-06-26",
        page_id="page-1",
        thread_type="inbox",
        role=None,
        include_inactive=False,
        alert_limit=20,
    )


def test_export_dashboard_report_api_maps_value_error_to_400(monkeypatch):
    monkeypatch.setattr(
        api,
        "export_dashboard_report_excel_service",
        AsyncMock(side_effect=ValueError("date_range_too_large")),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            api.export_dashboard_report(
                from_date="2025-01-01",
                to_date="2026-12-31",
                page_id=None,
                thread_type=None,
                role=None,
                include_inactive=False,
                alert_limit=20,
            )
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "date_range_too_large"


def test_export_dashboard_report_api_maps_unknown_error_to_500(monkeypatch):
    monkeypatch.setattr(
        api,
        "export_dashboard_report_excel_service",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            api.export_dashboard_report(
                from_date="2026-06-01",
                to_date="2026-06-26",
                page_id=None,
                thread_type=None,
                role=None,
                include_inactive=False,
                alert_limit=20,
            )
        )

    assert exc.value.status_code == 500
    assert exc.value.detail == "dashboard_report_export_failed"
