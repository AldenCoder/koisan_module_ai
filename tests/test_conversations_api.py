import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.schemas.conversation import (
    ConversationCreateRequest,
    ConversationListStatusFilterSchema,
    ConversationStatusSchema,
    ConversationUpdateRequest,
)
from app.api.v1 import conversations as conv_api
from app.models.conversations import Conversation, ConversationStatus


class _FakeConversation:
    def __init__(
        self,
        *,
        status=ConversationStatus.NEW,
        summaries=None,
        is_active=True,
        pancake_info_url=None,
        pancake_thread_type=None,
        order_note=None,
        version=None,
    ):
        now = datetime(2026, 4, 2, 10, 0, 0, tzinfo=timezone.utc)
        self.id = "conv-1"
        self.channel = "facebook"
        self.customer_name = "Nguyen Van A"
        self.customer_id = "fb_123"
        self.pancake_thread_type = pancake_thread_type
        self.pancake_info_url = pancake_info_url
        self.order_note = order_note
        self.is_active = is_active
        self.status = status
        self.summaries = summaries
        self.version = version
        self.created_at = now
        self.updated_at = now


def test_conversation_model_has_unique_pancake_thread_index():
    index_documents = [index.document for index in Conversation.Settings.indexes]

    assert {
        "key": {
            "pancake_page_id": 1,
            "pancake_conversation_id": 1,
        },
        "name": "uq_conv_pancake_thread",
        "unique": True,
        "partialFilterExpression": {
            "pancake_page_id": {"$type": "string"},
            "pancake_conversation_id": {"$type": "string"},
        },
    } in index_documents


def test_create_conversation_returns_created_item(monkeypatch):
    service_mock = AsyncMock(return_value=_FakeConversation())
    monkeypatch.setattr(conv_api, "create_conversation_crud_service", service_mock)

    payload = ConversationCreateRequest(
        channel="facebook",
        customer_name="Nguyen Van A",
        customer_id="fb_123",
        status=ConversationStatusSchema.NEW,
        summaries=["first summary"],
    )

    result = asyncio.run(conv_api.create_conversation(payload))

    assert result.id == "conv-1"
    assert result.status == ConversationStatusSchema.NEW
    assert result.customer_name == "Nguyen Van A"
    service_mock.assert_awaited_once()


def test_create_conversation_accepts_handover_status(monkeypatch):
    service_mock = AsyncMock(return_value=_FakeConversation(status=ConversationStatus.HANDOVER))
    monkeypatch.setattr(conv_api, "create_conversation_crud_service", service_mock)

    payload = ConversationCreateRequest(
        channel="facebook",
        customer_name="Nguyen Van A",
        customer_id="fb_123",
        status=ConversationStatusSchema.HANDOVER,
    )

    result = asyncio.run(conv_api.create_conversation(payload))

    assert result.status == ConversationStatusSchema.HANDOVER
    service_mock.assert_awaited_once()
    assert service_mock.await_args.kwargs["status"] == ConversationStatusSchema.HANDOVER


def test_create_conversation_accepts_apilimit_status(monkeypatch):
    service_mock = AsyncMock(return_value=_FakeConversation(status=ConversationStatus.APILIMIT))
    monkeypatch.setattr(conv_api, "create_conversation_crud_service", service_mock)

    payload = ConversationCreateRequest(
        channel="facebook",
        customer_name="Nguyen Van A",
        customer_id="fb_123",
        status=ConversationStatusSchema.APILIMIT,
    )

    result = asyncio.run(conv_api.create_conversation(payload))

    assert result.status == ConversationStatusSchema.APILIMIT
    service_mock.assert_awaited_once()
    assert service_mock.await_args.kwargs["status"] == ConversationStatusSchema.APILIMIT


def test_conversation_response_includes_pancake_info_url(monkeypatch):
    service_mock = AsyncMock(
        return_value=_FakeConversation(
            pancake_info_url="https://pancake.vn/970198996185881?c_id=970198996185881_1"
        )
    )
    monkeypatch.setattr(conv_api, "create_conversation_crud_service", service_mock)

    payload = ConversationCreateRequest(channel="facebook")

    result = asyncio.run(conv_api.create_conversation(payload))

    assert result.pancake_info_url == (
        "https://pancake.vn/970198996185881?c_id=970198996185881_1"
    )


def test_conversation_response_includes_pancake_thread_type(monkeypatch):
    service_mock = AsyncMock(
        return_value=_FakeConversation(pancake_thread_type="comment")
    )
    monkeypatch.setattr(conv_api, "create_conversation_crud_service", service_mock)

    payload = ConversationCreateRequest(channel="facebook")

    result = asyncio.run(conv_api.create_conversation(payload))

    assert result.pancake_thread_type == "comment"


def test_conversation_response_includes_order_note(monkeypatch):
    service_mock = AsyncMock(
        return_value=_FakeConversation(
            status=ConversationStatus.ORDER_PENDING,
            order_note="1. [10:05] Khách muốn đặt 2 ly matcha",
        )
    )
    monkeypatch.setattr(conv_api, "create_conversation_crud_service", service_mock)

    payload = ConversationCreateRequest(
        channel="facebook",
        status=ConversationStatusSchema.ORDER_PENDING,
    )

    result = asyncio.run(conv_api.create_conversation(payload))

    assert result.status == ConversationStatusSchema.ORDER_PENDING
    assert result.order_note == "1. [10:05] Khách muốn đặt 2 ly matcha"


def test_conversation_response_allows_missing_order_note(monkeypatch):
    service_mock = AsyncMock(return_value=_FakeConversation(order_note=None))
    monkeypatch.setattr(conv_api, "create_conversation_crud_service", service_mock)

    payload = ConversationCreateRequest(channel="facebook")

    result = asyncio.run(conv_api.create_conversation(payload))

    assert result.order_note is None


def test_conversation_response_includes_read_only_version(monkeypatch):
    service_mock = AsyncMock(return_value=_FakeConversation(version="1.1"))
    monkeypatch.setattr(conv_api, "create_conversation_crud_service", service_mock)

    payload = ConversationCreateRequest(channel="facebook")

    result = asyncio.run(conv_api.create_conversation(payload))

    assert result.version == "1.1"


def test_conversation_response_allows_missing_version(monkeypatch):
    service_mock = AsyncMock(return_value=_FakeConversation(version=None))
    monkeypatch.setattr(conv_api, "create_conversation_crud_service", service_mock)

    payload = ConversationCreateRequest(channel="facebook")

    result = asyncio.run(conv_api.create_conversation(payload))

    assert result.version is None


def test_conversation_create_update_requests_do_not_expose_internal_fields():
    create_payload = ConversationCreateRequest.model_validate(
        {
            "channel": "facebook",
            "pancake_info_url": "https://pancake.vn/page?c_id=conv",
            "pancake_thread_type": "comment",
            "version": "9.9",
        }
    )
    update_payload = ConversationUpdateRequest.model_validate(
        {
            "customer_name": "Nguyen Van B",
            "pancake_info_url": "https://pancake.vn/page?c_id=conv",
            "pancake_thread_type": "comment",
            "version": "9.9",
        }
    )

    assert "pancake_info_url" not in create_payload.model_dump()
    assert "pancake_thread_type" not in create_payload.model_dump()
    assert "version" not in create_payload.model_dump()
    assert "pancake_info_url" not in update_payload.model_dump(exclude_unset=True)
    assert "pancake_thread_type" not in update_payload.model_dump(exclude_unset=True)
    assert "version" not in update_payload.model_dump(exclude_unset=True)


def test_list_conversations_returns_message_count(monkeypatch):
    now = datetime(2026, 4, 2, 10, 0, 0, tzinfo=timezone.utc)
    service_mock = AsyncMock(
        return_value={
            "items": [
                {
                    "id": "conv-1",
                    "channel": "facebook",
                    "customer_name": "Nguyen Van A",
                    "customer_id": "fb_123",
                    "pancake_thread_type": "inbox",
                    "pancake_info_url": "https://pancake.vn/970198996185881?c_id=970198996185881_1",
                    "is_active": True,
                    "status": "new",
                    "summaries": ["abc"],
                    "version": "1.1",
                    "created_at": now,
                    "updated_at": now,
                    "message_count": 3,
                }
            ],
            "total": 1,
            "page": 1,
            "size": 10,
        }
    )
    monkeypatch.setattr(conv_api, "list_conversations_service", service_mock)

    result = asyncio.run(
        conv_api.list_conversations(
            status_filter=None,
            keyword=None,
            page=1,
            size=10,
            include_inactive=False,
        )
    )

    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].message_count == 3
    assert result.items[0].pancake_info_url == (
        "https://pancake.vn/970198996185881?c_id=970198996185881_1"
    )
    assert result.items[0].pancake_thread_type == "inbox"
    assert result.items[0].version == "1.1"


def test_get_conversation_returns_404_when_not_found(monkeypatch):
    monkeypatch.setattr(
        conv_api,
        "get_conversation_detail_service",
        AsyncMock(return_value=None),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(conv_api.get_conversation("missing-conv", include_inactive=True))

    assert exc.value.status_code == 404


def test_update_conversation_maps_value_error_to_400(monkeypatch):
    monkeypatch.setattr(
        conv_api,
        "update_conversation_crud_service",
        AsyncMock(side_effect=ValueError("Invalid status")),
    )

    payload = ConversationUpdateRequest(status=ConversationStatusSchema.CONFIRMED)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(conv_api.update_conversation("conv-1", payload))

    assert exc.value.status_code == 400


def test_update_conversation_accepts_handover_status(monkeypatch):
    service_mock = AsyncMock(return_value=_FakeConversation(status=ConversationStatus.HANDOVER))
    monkeypatch.setattr(conv_api, "update_conversation_crud_service", service_mock)

    payload = ConversationUpdateRequest(status=ConversationStatusSchema.HANDOVER)

    result = asyncio.run(conv_api.update_conversation("conv-1", payload))

    assert result.status == ConversationStatusSchema.HANDOVER
    service_mock.assert_awaited_once()
    assert service_mock.await_args.args == ("conv-1",)
    assert service_mock.await_args.kwargs["status"] == ConversationStatusSchema.HANDOVER


def test_update_conversation_accepts_apilimit_status(monkeypatch):
    service_mock = AsyncMock(return_value=_FakeConversation(status=ConversationStatus.APILIMIT))
    monkeypatch.setattr(conv_api, "update_conversation_crud_service", service_mock)

    payload = ConversationUpdateRequest(status=ConversationStatusSchema.APILIMIT)

    result = asyncio.run(conv_api.update_conversation("conv-1", payload))

    assert result.status == ConversationStatusSchema.APILIMIT
    service_mock.assert_awaited_once()
    assert service_mock.await_args.args == ("conv-1",)
    assert service_mock.await_args.kwargs["status"] == ConversationStatusSchema.APILIMIT


def test_list_conversations_accepts_handover_status_filter(monkeypatch):
    service_mock = AsyncMock(return_value={"items": [], "total": 0, "page": 1, "size": 10})
    monkeypatch.setattr(conv_api, "list_conversations_service", service_mock)

    result = asyncio.run(
        conv_api.list_conversations(
            status_filter=ConversationListStatusFilterSchema.HANDOVER,
            keyword=None,
            page=1,
            size=10,
            include_inactive=False,
        )
    )

    assert result.total == 0
    service_mock.assert_awaited_once()
    assert service_mock.await_args.kwargs["status"] == ConversationListStatusFilterSchema.HANDOVER


def test_list_conversations_accepts_apilimit_status_filter(monkeypatch):
    service_mock = AsyncMock(return_value={"items": [], "total": 0, "page": 1, "size": 10})
    monkeypatch.setattr(conv_api, "list_conversations_service", service_mock)

    result = asyncio.run(
        conv_api.list_conversations(
            status_filter=ConversationListStatusFilterSchema.APILIMIT,
            keyword=None,
            page=1,
            size=10,
            include_inactive=False,
        )
    )

    assert result.total == 0
    service_mock.assert_awaited_once()
    assert service_mock.await_args.kwargs["status"] == ConversationListStatusFilterSchema.APILIMIT


def test_list_conversations_accepts_confirmed_status_filter(monkeypatch):
    service_mock = AsyncMock(return_value={"items": [], "total": 0, "page": 1, "size": 10})
    monkeypatch.setattr(conv_api, "list_conversations_service", service_mock)

    result = asyncio.run(
        conv_api.list_conversations(
            status_filter=ConversationListStatusFilterSchema.CONFIRMED,
            keyword=None,
            page=1,
            size=10,
            include_inactive=False,
        )
    )

    assert result.total == 0
    service_mock.assert_awaited_once()
    assert service_mock.await_args.kwargs["status"] == ConversationListStatusFilterSchema.CONFIRMED


def test_list_conversations_accepts_order_pending_status_filter(monkeypatch):
    service_mock = AsyncMock(return_value={"items": [], "total": 0, "page": 1, "size": 10})
    monkeypatch.setattr(conv_api, "list_conversations_service", service_mock)

    result = asyncio.run(
        conv_api.list_conversations(
            status_filter=ConversationListStatusFilterSchema.ORDER_PENDING,
            keyword=None,
            page=1,
            size=10,
            include_inactive=False,
        )
    )

    assert result.total == 0
    service_mock.assert_awaited_once()
    assert service_mock.await_args.kwargs["status"] == ConversationListStatusFilterSchema.ORDER_PENDING


def test_list_status_filter_schema_only_allows_dashboard_statuses():
    assert {item.value for item in ConversationListStatusFilterSchema} == {
        "new",
        "handover",
        "apilimit",
        "confirmed",
        "order_pending",
    }


def test_delete_conversation_success(monkeypatch):
    monkeypatch.setattr(
        conv_api,
        "delete_conversation_service",
        AsyncMock(return_value=True),
    )

    result = asyncio.run(conv_api.delete_conversation("conv-1", soft_delete=True))

    assert result.deleted is True
    assert result.conversation_id == "conv-1"
    assert result.soft_delete is True


def test_get_conversation_returns_full_detail_and_messages(monkeypatch):
    now = datetime(2026, 4, 2, 10, 0, 0, tzinfo=timezone.utc)
    detail_data = {
        "conversation": {
            "id": "conv-1",
            "channel": "facebook",
            "customer_name": "Nguyen Van A",
            "customer_id": "fb_123",
            "pancake_info_url": "https://pancake.vn/970198996185881?c_id=970198996185881_1",
            "order_note": "1. [10:05] Khách muốn đặt 2 ly matcha",
            "is_active": True,
            "status": "new",
            "summaries": ["first"],
            "created_at": now,
            "updated_at": now,
        },
        "messages": [
            {
                "id": "msg-1",
                "conversation_id": "conv-1",
                "role": "user",
                "content": "hello",
                "meta": {},
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": "msg-2",
                "conversation_id": "conv-1",
                "role": "bot",
                "content": "hi",
                "meta": {},
                "created_at": now,
                "updated_at": now,
            },
        ],
        "conversation_states": [],
    }
    monkeypatch.setattr(
        conv_api,
        "get_conversation_detail_service",
        AsyncMock(return_value=detail_data),
    )

    result = asyncio.run(conv_api.get_conversation("conv-1", include_inactive=True))

    assert result.conversation.id == "conv-1"
    assert result.conversation.status == ConversationStatusSchema.NEW
    assert result.conversation.pancake_info_url == (
        "https://pancake.vn/970198996185881?c_id=970198996185881_1"
    )
    assert result.conversation.order_note == "1. [10:05] Khách muốn đặt 2 ly matcha"
    assert len(result.messages) == 2
    assert result.messages[0].id == "msg-1"
    assert result.messages[1].content == "hi"


def test_get_conversation_returns_handover_status(monkeypatch):
    now = datetime(2026, 4, 2, 10, 0, 0, tzinfo=timezone.utc)
    detail_data = {
        "conversation": {
            "id": "conv-1",
            "channel": "facebook",
            "customer_name": "Nguyen Van A",
            "customer_id": "fb_123",
            "is_active": True,
            "status": "handover",
            "summaries": None,
            "created_at": now,
            "updated_at": now,
        },
        "messages": [],
        "conversation_states": [],
    }
    monkeypatch.setattr(
        conv_api,
        "get_conversation_detail_service",
        AsyncMock(return_value=detail_data),
    )

    result = asyncio.run(conv_api.get_conversation("conv-1", include_inactive=True))

    assert result.conversation.status == ConversationStatusSchema.HANDOVER
