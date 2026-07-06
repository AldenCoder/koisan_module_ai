import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.models.messages import MessageRole
from app.services import ai_version_context_service as service


def test_compare_conversation_version_handles_missing_and_numeric_order():
    missing = service.compare_conversation_version(None, "1.1")
    assert missing.status == service.VERSION_STATUS_OLDER
    assert missing.conversation_version == "1.0"
    assert missing.system_version == "1.1"
    assert missing.should_upgrade is True

    newer = service.compare_conversation_version("1.10", "1.9")
    assert newer.status == service.VERSION_STATUS_NEWER
    assert newer.should_upgrade is False

    same_patch = service.compare_conversation_version("1.1.0", "1.1")
    assert same_patch.status == service.VERSION_STATUS_SAME


def test_compare_conversation_version_returns_invalid_reason():
    db_invalid = service.compare_conversation_version("v1", "1.1")
    assert db_invalid.status == service.VERSION_STATUS_INVALID
    assert db_invalid.reason.startswith("invalid_conversation_version:")

    env_invalid = service.compare_conversation_version("1.0", "bad")
    assert env_invalid.status == service.VERSION_STATUS_INVALID
    assert env_invalid.reason.startswith("invalid_system_version:")


def test_build_versioned_ai_user_trims_and_validates():
    assert (
        service.build_versioned_ai_user(
            " e8b3af1b-8978-4235-884e-fae3f33ef25f ",
            " 1.1 ",
        )
        == "e8b3af1b-8978-4235-884e-fae3f33ef25f:v1.1"
    )


def test_select_ai_user_for_existing_flow_uses_versioned_only_when_safe():
    same = service.select_ai_user_for_existing_flow(
        sender_id="customer-1",
        conversation_version="1.1",
        system_version="1.1",
    )
    assert same.ai_user == "customer-1:v1.1"
    assert same.status == service.VERSION_STATUS_SAME

    older = service.select_ai_user_for_existing_flow(
        sender_id="customer-1",
        conversation_version=None,
        system_version="1.1",
    )
    assert older.ai_user == "customer-1:v1.1"
    assert older.status == service.VERSION_STATUS_OLDER
    assert older.should_upgrade is True
    assert older.reason == "version_upgrade_required"


def test_reset_ai_initialization_for_version_session_persists_false_state():
    conversation = SimpleNamespace(
        fb_ai_initialized=True,
        fb_ai_initialized_at=datetime.now(timezone.utc),
        updated_at=None,
        save=AsyncMock(),
    )

    asyncio.run(service.reset_ai_initialization_for_version_session(conversation))

    assert conversation.fb_ai_initialized is False
    assert conversation.fb_ai_initialized_at is None
    assert conversation.updated_at is not None
    conversation.save.assert_awaited_once()


def test_sanitize_history_text_removes_urls_and_skips_link_only():
    assert service.sanitize_history_text(" Xem mẫu https://cdn.example.com/a.jpg nhé ") == "Xem mẫu nhé"
    assert service.sanitize_history_text("www.example.com/foo") == ""
    assert service.sanitize_history_text("https://cdn.example.com/a.jpg") == ""


class _Field:
    def __neg__(self):
        return self


class _HistoryQuery:
    def __init__(self, message_cls, query_filter):
        self.message_cls = message_cls
        self.query_filter = query_filter
        self.skip_value = 0
        self.limit_value = None

    def sort(self, *args, **kwargs):
        return self

    def skip(self, value):
        self.skip_value = int(value)
        return self

    def limit(self, value):
        self.limit_value = int(value)
        return self

    async def to_list(self):
        before_filter = self.query_filter.get("created_at") or {}
        before_created_at = before_filter.get("$lt")
        roles = set((self.query_filter.get("role") or {}).get("$in") or [])
        excluded_content = set((self.query_filter.get("content") or {}).get("$nin") or [])
        rows = [
            row
            for row in self.message_cls.rows
            if row.conversation_id == self.query_filter.get("conversation_id")
            and row.role in roles
            and row.content not in excluded_content
            and (before_created_at is None or row.created_at < before_created_at)
        ]
        rows.sort(key=lambda row: (row.created_at, row.id), reverse=True)
        if self.skip_value:
            rows = rows[self.skip_value :]
        if self.limit_value is not None:
            rows = rows[: self.limit_value]
        return rows


class _HistoryMessage:
    created_at = _Field()
    rows = []
    queries = []

    @classmethod
    def find(cls, query_filter):
        cls.queries.append(query_filter)
        return _HistoryQuery(cls, query_filter)


def test_get_text_history_items_sanitizes_limits_and_excludes_current(monkeypatch):
    monkeypatch.setattr(service, "Message", _HistoryMessage)
    base = datetime(2026, 6, 30, 8, 0, tzinfo=timezone.utc)
    current_id = "msg-current"
    _HistoryMessage.rows = [
        SimpleNamespace(
            id="msg-old",
            message_mid="mid-old",
            conversation_id="conv-1",
            role=MessageRole.USER.value,
            content="khách hỏi mã S2550542",
            created_at=base,
        ),
        SimpleNamespace(
            id="msg-link",
            message_mid="mid-link",
            conversation_id="conv-1",
            role=MessageRole.STAFF.value,
            content="https://cdn.example.com/photo.jpg",
            created_at=base + timedelta(minutes=1),
        ),
        SimpleNamespace(
            id="msg-mixed",
            message_mid="mid-mixed",
            conversation_id="conv-1",
            role=MessageRole.STAFF.value,
            content="Dạ mẫu này còn hàng https://cdn.example.com/p.jpg",
            created_at=base + timedelta(minutes=2),
        ),
        SimpleNamespace(
            id=current_id,
            message_mid="mid-current",
            conversation_id="conv-1",
            role=MessageRole.USER.value,
            content="current should not repeat",
            created_at=base + timedelta(minutes=3),
        ),
        SimpleNamespace(
            id="msg-other",
            message_mid="mid-other",
            conversation_id="conv-other",
            role=MessageRole.USER.value,
            content="không lấy conversation khác",
            created_at=base + timedelta(minutes=4),
        ),
        SimpleNamespace(
            id="msg-bot",
            message_mid="mid-bot",
            conversation_id="conv-1",
            role=MessageRole.BOT.value,
            content="Dạ mẫu này còn hàng",
            created_at=base + timedelta(minutes=5),
        ),
    ]

    items = asyncio.run(
        service.get_ai_version_text_history_items(
            conversation_id="conv-1",
            limit=3,
            exclude_message_ids=[current_id],
        )
    )

    assert [(item.role, item.content) for item in items] == [
        (MessageRole.USER.value, "khách hỏi mã S2550542"),
        (MessageRole.STAFF.value, "Dạ mẫu này còn hàng"),
        (MessageRole.BOT.value, "Dạ mẫu này còn hàng"),
    ]

    rendered = service.render_ai_version_context_message(
        history_items=items,
        current_message="Khách hỏi thêm màu đen",
    )
    assert rendered == (
        "Bối cảnh hội thoại trước khi cập nhật phiên bản AI:\n\n"
        "[Khách] khách hỏi mã S2550542\n"
        "[Nhân viên] Dạ mẫu này còn hàng\n"
        "[Bot] Dạ mẫu này còn hàng\n\n"
        "Tin nhắn hiện tại của khách:\n\n"
        "Khách hỏi thêm màu đen"
    )


def test_render_ai_version_context_message_returns_current_when_history_empty():
    assert (
        service.render_ai_version_context_message(
            history_items=[],
            current_message="Tin nhắn hiện tại https://cdn.example.com/a.jpg",
        )
        == "Tin nhắn hiện tại"
    )


class _UpgradeConversation:
    def __init__(self, *, version=None, initialized=True, save_error=None):
        self.id = "conv-upgrade"
        self.version = version
        self.fb_ai_initialized = initialized
        self.fb_ai_initialized_at = datetime.now(timezone.utc)
        self.updated_at = None
        self.save_error = save_error
        self.save_calls = []

    async def save(self):
        self.save_calls.append(
            {
                "version": self.version,
                "fb_ai_initialized": self.fb_ai_initialized,
                "fb_ai_initialized_at": self.fb_ai_initialized_at,
            }
        )
        if self.save_error:
            raise self.save_error


def test_prepare_ai_version_for_customer_message_runs_b1_b4(monkeypatch):
    service.clear_ai_version_upgrade_locks_for_tests()
    conversation = _UpgradeConversation(version=None, initialized=True)
    events = []

    async def fake_history(**kwargs):
        assert kwargs["conversation_id"] == "conv-upgrade"
        assert kwargs["exclude_message_mids"] == ["mid-current"]
        events.append(("history", kwargs["exclude_message_mids"]))
        return [
            service.AiVersionHistoryItem(
                role=MessageRole.USER.value,
                content="Khách hỏi mẫu https://cdn.example.com/old.jpg",
            ),
            service.AiVersionHistoryItem(
                role=MessageRole.STAFF.value,
                content="Dạ còn size M",
            ),
            service.AiVersionHistoryItem(
                role=MessageRole.BOT.value,
                content="Dạ em đã tư vấn size M",
            ),
        ]

    async def fake_init(active_conversation, ai_user):
        events.append(("init", active_conversation.fb_ai_initialized, ai_user))
        assert active_conversation.fb_ai_initialized is False
        assert active_conversation.fb_ai_initialized_at is None
        active_conversation.fb_ai_initialized = True
        active_conversation.fb_ai_initialized_at = datetime.now(timezone.utc)
        await active_conversation.save()
        return {"ok": True}

    async def fake_send(active_conversation, ai_user, content, purpose):
        events.append(("send", ai_user, content, purpose))
        assert ai_user == "customer-1:v1.1"
        assert purpose == "user_message"
        assert "https://" not in content
        assert "[Khách] Khách hỏi mẫu" in content
        assert "[Bot] Dạ em đã tư vấn size M" in content
        assert "Tin nhắn hiện tại của khách" in content
        assert "Khách hỏi thêm màu đen" in content
        return {"ok": True, "response_data": {"text": "Dạ mẫu này còn ạ"}}

    monkeypatch.setattr(service, "get_ai_version_text_history_items", fake_history)

    result = asyncio.run(
        service.prepare_ai_version_for_customer_message(
            conversation=conversation,
            sender_id="customer-1",
            current_message="Khách hỏi thêm màu đen https://cdn.example.com/new.jpg",
            message_mid="mid-current",
            exclude_message_mids=["mid-current"],
            init_ai_session=fake_init,
            send_ai_message=fake_send,
            system_version="1.1",
            purpose="user_message",
        )
    )

    assert result["ok"] is True
    assert result["upgraded"] is True
    assert result["ai_user"] == "customer-1:v1.1"
    assert result["history_count"] == 3
    assert conversation.version == "1.1"
    assert events[0] == ("init", False, "customer-1:v1.1")
    assert events[1] == ("history", ["mid-current"])
    assert events[2][0] == "send"


def test_prepare_ai_version_for_customer_message_keeps_old_version_when_context_fails(
    monkeypatch,
):
    service.clear_ai_version_upgrade_locks_for_tests()
    conversation = _UpgradeConversation(version="1.0", initialized=True)

    monkeypatch.setattr(
        service,
        "get_ai_version_text_history_items",
        AsyncMock(return_value=[]),
    )

    async def fake_init(active_conversation, ai_user):
        active_conversation.fb_ai_initialized = True
        return {"ok": True}

    async def fake_send(active_conversation, ai_user, content, purpose):
        return {"ok": False, "reason": "ai_down"}

    result = asyncio.run(
        service.prepare_ai_version_for_customer_message(
            conversation=conversation,
            sender_id="customer-1",
            current_message="Tin text",
            init_ai_session=fake_init,
            send_ai_message=fake_send,
            system_version="1.1",
        )
    )

    assert result["ok"] is False
    assert result["reason"] == "ai_version_context_call_failed"
    assert conversation.version == "1.0"


def test_prepare_ai_version_for_customer_message_falls_back_to_current_when_history_fails(
    monkeypatch,
):
    service.clear_ai_version_upgrade_locks_for_tests()
    conversation = _UpgradeConversation(version="1.0", initialized=True)
    sent = {}

    monkeypatch.setattr(
        service,
        "get_ai_version_text_history_items",
        AsyncMock(side_effect=RuntimeError("db down")),
    )

    async def fake_init(active_conversation, ai_user):
        active_conversation.fb_ai_initialized = True
        return {"ok": True}

    async def fake_send(active_conversation, ai_user, content, purpose):
        sent["content"] = content
        return {"ok": True, "response_data": {"text": "ok"}}

    result = asyncio.run(
        service.prepare_ai_version_for_customer_message(
            conversation=conversation,
            sender_id="customer-1",
            current_message="Chỉ gửi current",
            init_ai_session=fake_init,
            send_ai_message=fake_send,
            system_version="1.1",
        )
    )

    assert result["ok"] is True
    assert result["upgraded"] is True
    assert result["history_count"] == 0
    assert result["history_reason"] == "history_query_failed"
    assert sent["content"] == "Chỉ gửi current"
    assert conversation.version == "1.1"


def test_prepare_ai_version_for_customer_message_serializes_concurrent_upgrade(monkeypatch):
    service.clear_ai_version_upgrade_locks_for_tests()
    conversation = _UpgradeConversation(version=None, initialized=True)
    send_entered = asyncio.Event()
    release_send = asyncio.Event()
    events = []

    monkeypatch.setattr(
        service,
        "get_ai_version_text_history_items",
        AsyncMock(return_value=[]),
    )

    async def fake_init(active_conversation, ai_user):
        events.append(("init", ai_user))
        active_conversation.fb_ai_initialized = True
        return {"ok": True}

    async def fake_send(active_conversation, ai_user, content, purpose):
        events.append(("send", ai_user, content))
        send_entered.set()
        await release_send.wait()
        return {"ok": True, "response_data": {"text": "ok"}}

    async def run_two():
        first = asyncio.create_task(
            service.prepare_ai_version_for_customer_message(
                conversation=conversation,
                sender_id="customer-1",
                current_message="Tin 1",
                message_mid="mid-1",
                init_ai_session=fake_init,
                send_ai_message=fake_send,
                system_version="1.1",
            )
        )
        await send_entered.wait()
        second = asyncio.create_task(
            service.prepare_ai_version_for_customer_message(
                conversation=conversation,
                sender_id="customer-1",
                current_message="Tin 2",
                message_mid="mid-2",
                init_ai_session=fake_init,
                send_ai_message=fake_send,
                system_version="1.1",
            )
        )
        await asyncio.sleep(0)
        release_send.set()
        return await asyncio.gather(first, second)

    first_result, second_result = asyncio.run(run_two())

    assert first_result["upgraded"] is True
    assert second_result["upgraded"] is False
    assert second_result["reason"] == "version_already_current_after_lock"
    assert second_result["ai_user"] == "customer-1:v1.1"
    assert [event[0] for event in events] == ["init", "send"]
