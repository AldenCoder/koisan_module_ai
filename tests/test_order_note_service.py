import asyncio
from datetime import datetime, timezone

import pytest

from app.models.conversations import ConversationStatus
from app.services import order_note_service as ons


class _FakeConversation:
    def __init__(
        self,
        *,
        conversation_id="conv-1",
        status=ConversationStatus.NEW,
        order_note=None,
    ):
        self.id = conversation_id
        self.status = status
        self.order_note = order_note
        self.updated_at = datetime(2026, 5, 18, 10, 0, 0, tzinfo=timezone.utc)
        self.save_count = 0

    async def save(self):
        self.save_count += 1


def test_create_order_note_service_sets_order_pending_for_first_note(monkeypatch):
    conversation = _FakeConversation()
    now = datetime(2026, 5, 18, 10, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(ons, "now_vn", lambda: now)

    async def fake_get_conversation(conversation_id, **kwargs):
        assert conversation_id == "conv-1"
        return conversation

    monkeypatch.setattr(ons, "get_conversation_by_id_service", fake_get_conversation)

    result = asyncio.run(
        ons.create_order_note_service(
            conversation_id=" conv-1 ",
            order_note=" Khách muốn đặt 2 ly matcha ",
        )
    )

    assert result["success"] is True
    assert result["conversation_id"] == "conv-1"
    assert result["status"] == "order_pending"
    assert result["order_note_index"] == 1
    assert result["order_note"] == "1. [10:05] Khách muốn đặt 2 ly matcha"
    assert conversation.status == ConversationStatus.ORDER_PENDING
    assert conversation.order_note == "1. [10:05] Khách muốn đặt 2 ly matcha"
    assert conversation.updated_at == now
    assert conversation.save_count == 1


def test_create_order_note_service_appends_next_note_when_pending(monkeypatch):
    conversation = _FakeConversation(
        status=ConversationStatus.ORDER_PENDING,
        order_note="1. [10:05] Khách muốn đặt 2 ly matcha",
    )
    monkeypatch.setattr(ons, "now_vn", lambda: datetime(2026, 5, 18, 10, 20, tzinfo=timezone.utc))
    monkeypatch.setattr(
        ons,
        "get_conversation_by_id_service",
        lambda *args, **kwargs: _async_return(conversation),
    )

    result = asyncio.run(
        ons.create_order_note_service(
            conversation_id="conv-1",
            order_note="Khách đặt thêm 1 bánh tiramisu",
        )
    )

    assert result["order_note_index"] == 2
    assert result["order_note"] == (
        "1. [10:05] Khách muốn đặt 2 ly matcha\n"
        "2. [10:20] Khách đặt thêm 1 bánh tiramisu"
    )
    assert conversation.order_note == result["order_note"]
    assert conversation.save_count == 1


def test_create_order_note_service_resets_note_when_status_is_not_pending(monkeypatch):
    conversation = _FakeConversation(
        status=ConversationStatus.NEW,
        order_note="1. [09:00] Note cũ đã xử lý",
    )
    monkeypatch.setattr(ons, "now_vn", lambda: datetime(2026, 5, 18, 11, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(
        ons,
        "get_conversation_by_id_service",
        lambda *args, **kwargs: _async_return(conversation),
    )

    result = asyncio.run(
        ons.create_order_note_service(
            conversation_id="conv-1",
            order_note="Khách đặt đơn mới",
        )
    )

    assert result["order_note_index"] == 1
    assert result["order_note"] == "1. [11:00] Khách đặt đơn mới"
    assert conversation.order_note == "1. [11:00] Khách đặt đơn mới"


def test_create_order_note_service_uses_next_index_after_three_existing_lines(monkeypatch):
    conversation = _FakeConversation(
        status=ConversationStatus.ORDER_PENDING,
        order_note=(
            "1. [10:05] Đơn đầu\n"
            "2. [10:20] Đơn hai\n"
            "3. [10:35] Đơn ba"
        ),
    )
    monkeypatch.setattr(ons, "now_vn", lambda: datetime(2026, 5, 18, 10, 45, tzinfo=timezone.utc))
    monkeypatch.setattr(
        ons,
        "get_conversation_by_id_service",
        lambda *args, **kwargs: _async_return(conversation),
    )

    result = asyncio.run(
        ons.create_order_note_service(
            conversation_id="conv-1",
            order_note="Đơn bốn",
        )
    )

    assert result["order_note_index"] == 4
    assert result["order_note"].endswith("\n4. [10:45] Đơn bốn")


def test_create_order_note_service_returns_not_found_without_update(monkeypatch, caplog):
    caplog.set_level("WARNING", logger="address_logger")

    async def fake_get_conversation(*args, **kwargs):
        return None

    monkeypatch.setattr(ons, "get_conversation_by_id_service", fake_get_conversation)

    result = asyncio.run(
        ons.create_order_note_service(
            conversation_id="missing-conv",
            order_note="Khách muốn đặt 2 ly matcha",
        )
    )

    assert result["success"] is False
    assert result["reason"] == "conversation_not_found"
    assert "ORDER_NOTE_CONVERSATION_NOT_FOUND" in caplog.text


def test_create_order_note_service_invalid_id_logs_and_raises(monkeypatch, caplog):
    caplog.set_level("WARNING", logger="address_logger")

    async def fake_get_conversation(*args, **kwargs):
        raise ValueError("Invalid conversation_id format")

    monkeypatch.setattr(ons, "get_conversation_by_id_service", fake_get_conversation)

    with pytest.raises(ons.OrderNoteConversationIdInvalid):
        asyncio.run(
            ons.create_order_note_service(
                conversation_id="bad-id",
                order_note="Khách muốn đặt 2 ly matcha",
            )
        )

    assert "ORDER_NOTE_CONVERSATION_ID_INVALID" in caplog.text


def test_create_order_note_service_rejects_empty_order_note(monkeypatch):
    conversation = _FakeConversation()
    monkeypatch.setattr(
        ons,
        "get_conversation_by_id_service",
        lambda *args, **kwargs: _async_return(conversation),
    )

    with pytest.raises(ValueError, match="order_note is required"):
        asyncio.run(
            ons.create_order_note_service(
                conversation_id="conv-1",
                order_note="   ",
            )
        )

    assert conversation.save_count == 0


async def _async_return(value):
    return value
