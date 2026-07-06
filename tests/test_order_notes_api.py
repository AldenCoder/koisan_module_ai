import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.schemas.order_note import OrderNoteCreateRequest
from app.api.v1 import order_notes as order_notes_api
from app.services.order_note_service import OrderNoteConversationIdInvalid


def test_order_notes_route_uses_no_trailing_slash(monkeypatch):
    service_mock = AsyncMock(
        return_value={
            "success": True,
            "conversation_id": "conv-1",
            "status": "order_pending",
            "order_note": "1. [10:05] Customer wants 2 matcha",
            "order_note_index": 1,
        }
    )
    monkeypatch.setattr(order_notes_api, "create_order_note_service", service_mock)

    app = FastAPI()
    app.include_router(order_notes_api.router, prefix="/api/v1/order-notes")
    client = TestClient(app)

    response = client.post(
        "/api/v1/order-notes",
        json={
            "conversation_id": "conv-1",
            "order_note": "Customer wants 2 matcha",
        },
    )

    assert response.status_code == 201
    assert response.json()["conversation_id"] == "conv-1"
    service_mock.assert_awaited_once_with(
        conversation_id="conv-1",
        order_note="Customer wants 2 matcha",
    )


def test_create_order_note_api_returns_response(monkeypatch):
    service_mock = AsyncMock(
        return_value={
            "success": True,
            "conversation_id": "conv-1",
            "status": "order_pending",
            "order_note": "1. [10:05] Khách muốn đặt 2 ly matcha",
            "order_note_index": 1,
        }
    )
    monkeypatch.setattr(order_notes_api, "create_order_note_service", service_mock)

    payload = OrderNoteCreateRequest(
        conversation_id="conv-1",
        order_note="Khách muốn đặt 2 ly matcha",
    )

    result = asyncio.run(order_notes_api.create_order_note(payload))

    assert result.success is True
    assert result.conversation_id == "conv-1"
    assert result.status == "order_pending"
    assert result.order_note_index == 1
    service_mock.assert_awaited_once_with(
        conversation_id="conv-1",
        order_note="Khách muốn đặt 2 ly matcha",
    )


def test_create_order_note_api_maps_invalid_id_to_400(monkeypatch):
    monkeypatch.setattr(
        order_notes_api,
        "create_order_note_service",
        AsyncMock(side_effect=OrderNoteConversationIdInvalid("Invalid conversation_id format")),
    )
    payload = OrderNoteCreateRequest(
        conversation_id="bad-id",
        order_note="Khách muốn đặt 2 ly matcha",
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(order_notes_api.create_order_note(payload))

    assert exc.value.status_code == 400


def test_create_order_note_api_maps_not_found_to_404(monkeypatch):
    monkeypatch.setattr(
        order_notes_api,
        "create_order_note_service",
        AsyncMock(
            return_value={
                "success": False,
                "reason": "conversation_not_found",
                "conversation_id": "missing-conv",
            }
        ),
    )
    payload = OrderNoteCreateRequest(
        conversation_id="missing-conv",
        order_note="Khách muốn đặt 2 ly matcha",
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(order_notes_api.create_order_note(payload))

    assert exc.value.status_code == 404


def test_order_note_create_request_rejects_extra_fields():
    with pytest.raises(ValidationError):
        OrderNoteCreateRequest.model_validate(
            {
                "conversation_id": "conv-1",
                "order_note": "Khách muốn đặt 2 ly matcha",
                "customer_id": "fb-123",
            }
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"order_note": "Khách muốn đặt 2 ly matcha"},
        {"conversation_id": "conv-1"},
    ],
)
def test_order_note_create_request_rejects_missing_required_fields(payload):
    with pytest.raises(ValidationError):
        OrderNoteCreateRequest.model_validate(payload)
