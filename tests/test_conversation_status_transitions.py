import asyncio
from datetime import datetime, timezone

import pytest

from app.models.conversations import ConversationStatus
from app.services import conversation_service as cs


class _FakeConversation:
    def __init__(self, *, status, order_note=None):
        self.id = "conv-1"
        self.status = status
        self.order_note = order_note
        self.updated_at = datetime(2026, 5, 18, 10, 0, 0, tzinfo=timezone.utc)
        self.save_count = 0

    async def save(self):
        self.save_count += 1


def test_update_conversation_allows_confirmed_from_handover(monkeypatch):
    conversation = _FakeConversation(status=ConversationStatus.HANDOVER)

    async def fake_get_conversation(*args, **kwargs):
        return conversation

    monkeypatch.setattr(cs, "get_conversation_by_id_service", fake_get_conversation)

    result = asyncio.run(
        cs.update_conversation_crud_service(
            "conv-1",
            status=ConversationStatus.CONFIRMED,
        )
    )

    assert result is conversation
    assert conversation.status == ConversationStatus.CONFIRMED
    assert conversation.save_count == 1


def test_update_conversation_allows_confirmed_from_apilimit(monkeypatch):
    conversation = _FakeConversation(status=ConversationStatus.APILIMIT)

    async def fake_get_conversation(*args, **kwargs):
        return conversation

    monkeypatch.setattr(cs, "get_conversation_by_id_service", fake_get_conversation)

    result = asyncio.run(
        cs.update_conversation_crud_service(
            "conv-1",
            status=ConversationStatus.CONFIRMED,
        )
    )

    assert result is conversation
    assert conversation.status == ConversationStatus.CONFIRMED
    assert conversation.save_count == 1


def test_update_conversation_rejects_confirmed_from_new(monkeypatch):
    conversation = _FakeConversation(status=ConversationStatus.NEW)

    async def fake_get_conversation(*args, **kwargs):
        return conversation

    monkeypatch.setattr(cs, "get_conversation_by_id_service", fake_get_conversation)

    with pytest.raises(ValueError, match="only be confirmed from handover or apilimit"):
        asyncio.run(
            cs.update_conversation_crud_service(
                "conv-1",
                status=ConversationStatus.CONFIRMED,
            )
        )

    assert conversation.status == ConversationStatus.NEW
    assert conversation.save_count == 0


def test_update_conversation_allows_confirmed_noop(monkeypatch):
    conversation = _FakeConversation(status=ConversationStatus.CONFIRMED)

    async def fake_get_conversation(*args, **kwargs):
        return conversation

    monkeypatch.setattr(cs, "get_conversation_by_id_service", fake_get_conversation)

    result = asyncio.run(
        cs.update_conversation_crud_service(
            "conv-1",
            status=ConversationStatus.CONFIRMED,
        )
    )

    assert result is conversation
    assert conversation.status == ConversationStatus.CONFIRMED
    assert conversation.save_count == 0


def test_update_conversation_clears_order_note_when_order_pending_returns_new(monkeypatch):
    conversation = _FakeConversation(
        status=ConversationStatus.ORDER_PENDING,
        order_note="1. [10:05] Khách muốn đặt 2 ly matcha",
    )

    async def fake_get_conversation(*args, **kwargs):
        return conversation

    monkeypatch.setattr(cs, "get_conversation_by_id_service", fake_get_conversation)

    result = asyncio.run(
        cs.update_conversation_crud_service(
            "conv-1",
            status=ConversationStatus.NEW,
        )
    )

    assert result is conversation
    assert conversation.status == ConversationStatus.NEW
    assert conversation.order_note is None
    assert conversation.save_count == 1


def test_update_conversation_keeps_order_note_when_updating_profile(monkeypatch):
    conversation = _FakeConversation(
        status=ConversationStatus.ORDER_PENDING,
        order_note="1. [10:05] Khách muốn đặt 2 ly matcha",
    )
    conversation.customer_name = "Nguyen Van A"

    async def fake_get_conversation(*args, **kwargs):
        return conversation

    monkeypatch.setattr(cs, "get_conversation_by_id_service", fake_get_conversation)

    result = asyncio.run(
        cs.update_conversation_crud_service(
            "conv-1",
            customer_name="Nguyen Van B",
        )
    )

    assert result is conversation
    assert conversation.status == ConversationStatus.ORDER_PENDING
    assert conversation.order_note == "1. [10:05] Khách muốn đặt 2 ly matcha"
    assert conversation.customer_name == "Nguyen Van B"
    assert conversation.save_count == 1


def test_update_conversation_keeps_order_note_when_status_remains_order_pending(monkeypatch):
    conversation = _FakeConversation(
        status=ConversationStatus.ORDER_PENDING,
        order_note="1. [10:05] Khách muốn đặt 2 ly matcha",
    )

    async def fake_get_conversation(*args, **kwargs):
        return conversation

    monkeypatch.setattr(cs, "get_conversation_by_id_service", fake_get_conversation)

    result = asyncio.run(
        cs.update_conversation_crud_service(
            "conv-1",
            status=ConversationStatus.ORDER_PENDING,
        )
    )

    assert result is conversation
    assert conversation.status == ConversationStatus.ORDER_PENDING
    assert conversation.order_note == "1. [10:05] Khách muốn đặt 2 ly matcha"
    assert conversation.save_count == 0


def test_removed_interest_statuses_are_not_valid():
    with pytest.raises(ValueError):
        ConversationStatus("not_interested")
    with pytest.raises(ValueError):
        ConversationStatus("highly_interested")
