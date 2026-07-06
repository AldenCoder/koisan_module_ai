import asyncio
import json
from datetime import timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.api.v1 import facebook_webhook as fw
from app.api.dependencies.time import now_vn
from app.services import ai_version_context_service as version_service


class _FakeConversation:
    def __init__(self, *, initialized: bool, paused_until=None, version=None):
        self.id = "conv-1"
        self.fb_ai_initialized = initialized
        self.fb_ai_initialized_at = None
        self.bot_paused_until = paused_until
        self.bot_paused_at = None
        self.bot_paused_reason = None
        self.bot_paused_by = None
        self.customer_id = "fb_user_1"
        self.version = version
        self.updated_at = None
        self.save_called = 0

    async def save(self):
        self.save_called += 1


class _FakeRequest:
    def __init__(self, payload):
        self.client = SimpleNamespace(host="127.0.0.1")
        self.url = SimpleNamespace(path="/api/v1/facebook/webhook")
        self._payload = payload

    async def body(self):
        return json.dumps(self._payload).encode("utf-8")


def test_extract_incoming_messages_returns_all_messages_sorted_by_timestamp():
    payload = {
        "object": "page",
        "entry": [
            {
                "id": "page-1",
                "messaging": [
                    {
                        "sender": {"id": "user-1"},
                        "recipient": {"id": "page-1"},
                        "timestamp": 200,
                        "message": {"mid": "m2", "text": "tin nhan 2"},
                    },
                    {
                        "sender": {"id": "user-1"},
                        "recipient": {"id": "page-1"},
                        "timestamp": 100,
                        "message": {"mid": "m1", "text": "tin nhan 1"},
                    },
                ],
            }
        ],
    }

    messages = fw._extract_incoming_messages(payload)

    assert [item["message_mid"] for item in messages] == ["m1", "m2"]
    assert [item["text"] for item in messages] == ["tin nhan 1", "tin nhan 2"]


def test_extract_incoming_messages_includes_metadata_and_app_id():
    payload = {
        "entry": [
            {
                "id": "page-1",
                "messaging": [
                    {
                        "sender": {"id": "page-1"},
                        "recipient": {"id": "user-1"},
                        "timestamp": 100,
                        "message": {
                            "mid": "m_echo",
                            "is_echo": True,
                            "text": "bot reply",
                            "metadata": "source_mid:m_customer",
                            "app_id": 12345,
                        },
                    }
                ],
            }
        ]
    }

    messages = fw._extract_incoming_messages(payload)

    assert messages[0]["metadata"] == "source_mid:m_customer"
    assert messages[0]["app_id"] == 12345
    assert messages[0]["raw"]["message"]["app_id"] == 12345


def test_classify_facebook_message_detects_customer_message():
    latest = {"is_echo": False, "sender_id": "user-1", "page_id": "page-1"}

    assert fw._classify_facebook_message(latest) == fw.FACEBOOK_MESSAGE_CUSTOMER


def test_classify_facebook_message_detects_bot_echo():
    latest = {
        "is_echo": True,
        "sender_id": "page-1",
        "page_id": "page-1",
        "metadata": "source_mid:m_customer",
    }

    assert fw._classify_facebook_message(latest) == fw.FACEBOOK_MESSAGE_BOT_ECHO


def test_classify_facebook_message_detects_admin_message():
    latest = {
        "is_echo": True,
        "sender_id": "page-1",
        "page_id": "page-1",
        "metadata": "",
    }

    assert fw._classify_facebook_message(latest) == fw.FACEBOOK_MESSAGE_ADMIN


def test_is_bot_paused_treats_naive_mongo_datetime_as_utc():
    current_time = now_vn()
    paused_until_utc_naive = (
        current_time + timedelta(minutes=5)
    ).astimezone(timezone.utc).replace(tzinfo=None)
    conversation = _FakeConversation(
        initialized=True,
        paused_until=paused_until_utc_naive,
    )

    assert fw._is_bot_paused(conversation, current_time=current_time) is True


def test_resume_conversation_does_not_clear_naive_utc_pause_before_expiry():
    current_time = now_vn()
    paused_until_utc_naive = (
        current_time + timedelta(minutes=5)
    ).astimezone(timezone.utc).replace(tzinfo=None)
    conversation = _FakeConversation(
        initialized=True,
        paused_until=paused_until_utc_naive,
    )
    conversation.bot_paused_at = current_time - timedelta(minutes=1)
    conversation.bot_paused_reason = "admin_message"
    conversation.bot_paused_by = "page-1"

    result = asyncio.run(
        fw._resume_conversation_if_pause_expired(
            conversation,
            current_time=current_time,
        )
    )

    assert result is False
    assert conversation.bot_paused_until == paused_until_utc_naive
    assert conversation.bot_paused_reason == "admin_message"
    assert conversation.save_called == 0


def test_get_or_create_conversation_from_admin_echo_preserves_existing_channel(monkeypatch):
    existing_conversation = _FakeConversation(initialized=True)
    existing_conversation.channel = "MediaX AI chatbot testing"

    class _Field:
        def __eq__(self, other):
            return ("customer_id", other)

        def __neg__(self):
            return self

    class _Query:
        def sort(self, *args, **kwargs):
            return self

        async def first_or_none(self):
            return existing_conversation

    class _FakeConversationModel:
        customer_id = _Field()
        updated_at = _Field()

        @classmethod
        def find(cls, *args, **kwargs):
            return _Query()

    monkeypatch.setattr(fw, "Conversation", _FakeConversationModel)

    result = asyncio.run(
        fw._get_or_create_conversation_from_admin_echo(
            {
                "recipient_id": "24472953752402662",
                "page_id": "970198996185881",
            }
        )
    )

    assert result is existing_conversation
    assert existing_conversation.channel == "MediaX AI chatbot testing"
    assert existing_conversation.save_called == 0


def test_build_ai_chat_payload_appends_test_mode_note_for_normal_messages():
    original = "  giữ nguyên 100% nội dung user  "
    expected_content = f"{original}\n\n{fw.FB_AI_TEST_MODE_NOTE}"

    payload = fw._build_ai_chat_payload(user="fb_user_123", content=original)

    assert payload == {
        "user": "fb_user_123",
        "messages": [{"role": "user", "content": expected_content}],
        "stream": False,
    }


def test_build_ai_chat_payload_appends_conversation_id_for_normal_messages():
    original = "khách muốn đặt 2 ly matcha"
    expected_content = (
        f"{original}\n\n"
        f"{fw.FB_AI_TEST_MODE_NOTE}, conversation_id: conv-123"
    )

    payload = fw._build_ai_chat_payload(
        user="fb_user_123",
        content=original,
        conversation_id=" conv-123 ",
    )

    assert payload["messages"][0]["content"] == expected_content


def test_build_ai_chat_payload_does_not_append_note_for_init_message():
    payload = fw._build_ai_chat_payload(user="fb_user_123", content=fw.FB_AI_INIT_MESSAGE)

    assert payload == {
        "user": "fb_user_123",
        "messages": [{"role": "user", "content": fw.FB_AI_INIT_MESSAGE}],
        "stream": False,
    }


def test_build_ai_chat_payload_does_not_append_conversation_id_for_init_message():
    payload = fw._build_ai_chat_payload(
        user="fb_user_123",
        content=fw.FB_AI_INIT_MESSAGE,
        conversation_id="conv-123",
    )

    assert payload == {
        "user": "fb_user_123",
        "messages": [{"role": "user", "content": fw.FB_AI_INIT_MESSAGE}],
        "stream": False,
    }


def test_extract_text_from_ai_response_supports_openai_choices_content_blocks():
    response_data = {
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "text", "text": "Xin chào bạn"},
                    ]
                }
            }
        ]
    }

    assert fw._extract_text_from_ai_response(response_data) == "Xin chào bạn"


def test_run_ai_forward_and_reply_keeps_ai_text_before_send(monkeypatch):
    latest = {
        "sender_id": "fb_user_1",
        "message_mid": "m_001",
        "page_id": "page_1",
        "text": "xin chao",
    }

    class _Conversation:
        id = "conv-1"

    sent: dict = {}
    saved: dict = {}

    async def fake_get_or_create_sender_conversation(_latest):
        return _Conversation()

    async def fake_ensure_sender_initialized(*, latest, conversation):
        assert latest["sender_id"] == "fb_user_1"
        assert conversation.id == "conv-1"
        return {"ok": True, "reason": "already_initialized"}

    async def fake_post_ai_chat_with_retry(*, payload, sender_id, message_mid, purpose):
        assert payload["user"] == "fb_user_1"
        assert payload["messages"][0]["content"] == (
            "xin chao\n\n"
            f"{fw.FB_AI_TEST_MODE_NOTE}, conversation_id: conv-1"
        )
        assert sender_id == "fb_user_1"
        assert message_mid == "m_001"
        assert purpose == "user_message"
        return {
            "ok": True,
            "response_data": {
                "choices": [
                    {
                        "message": {
                            "content": "Dạ *chào* bạn #ạ",
                        }
                    }
                ]
            },
        }

    async def fake_send_facebook_reply(*, recipient_id, message_text, reply_to_mid, image_urls=None):
        sent["recipient_id"] = recipient_id
        sent["message_text"] = message_text
        sent["reply_to_mid"] = reply_to_mid
        sent["image_urls"] = image_urls
        return {"ok": True}

    async def fake_save_forwarded_messages(*, conversation, latest, assistant_message):
        saved["conversation_id"] = conversation.id
        saved["latest_mid"] = latest["message_mid"]
        saved["assistant_message"] = assistant_message

    monkeypatch.setattr(fw, "_get_or_create_sender_conversation", fake_get_or_create_sender_conversation)
    monkeypatch.setattr(fw, "_ensure_sender_initialized", fake_ensure_sender_initialized)
    monkeypatch.setattr(fw, "_post_ai_chat_with_retry", fake_post_ai_chat_with_retry)
    monkeypatch.setattr(fw, "_send_facebook_reply", fake_send_facebook_reply)
    monkeypatch.setattr(fw, "_save_forwarded_messages", fake_save_forwarded_messages)

    result = asyncio.run(fw._run_ai_forward_and_reply(latest))

    assert result["ok"] is True
    assert result["assistant_message"] == "Dạ *chào* bạn #ạ"
    assert sent == {
        "recipient_id": "fb_user_1",
        "message_text": "Dạ *chào* bạn #ạ",
        "reply_to_mid": "m_001",
        "image_urls": [],
    }
    assert saved == {
        "conversation_id": "conv-1",
        "latest_mid": "m_001",
        "assistant_message": "Dạ *chào* bạn #ạ",
    }


def test_run_ai_forward_and_reply_upgrades_old_conversation_version(monkeypatch):
    version_service.clear_ai_version_upgrade_locks_for_tests()
    latest = {
        "sender_id": "fb_user_1",
        "message_mid": "m_upgrade",
        "page_id": "page_1",
        "text": "Khách hỏi tiếp màu đen",
    }
    conversation = _FakeConversation(initialized=True, version="1.0")
    events = []
    sent: dict = {}

    async def fake_history(**kwargs):
        assert kwargs["conversation_id"] == "conv-1"
        assert kwargs["exclude_message_mids"] == ["m_upgrade"]
        return [
            version_service.AiVersionHistoryItem(
                role="user",
                content="Khách hỏi mã S2550542 https://cdn.example.com/a.jpg",
            ),
            version_service.AiVersionHistoryItem(
                role="staff",
                content="Dạ mẫu này còn hàng",
            ),
        ]

    async def fake_get_or_create_sender_conversation(_latest):
        return conversation

    async def fake_reload(_conversation):
        return _conversation

    async def fake_ensure_sender_initialized(*, latest, conversation, ai_user=None):
        events.append(("init", ai_user, conversation.fb_ai_initialized))
        assert ai_user == "fb_user_1:v1.1"
        assert conversation.fb_ai_initialized is False
        conversation.fb_ai_initialized = True
        return {"ok": True, "reason": "initialized_now"}

    async def fake_post_ai_chat_with_retry(*, payload, sender_id, message_mid, purpose):
        events.append(("post", sender_id, payload["messages"][0]["content"], purpose))
        assert payload["user"] == "fb_user_1:v1.1"
        assert sender_id == "fb_user_1:v1.1"
        assert message_mid == "m_upgrade"
        assert purpose == "user_message"
        content = payload["messages"][0]["content"]
        assert "Bối cảnh hội thoại trước khi cập nhật phiên bản AI" in content
        assert "https://" not in content
        assert "Khách hỏi tiếp màu đen" in content
        return {"ok": True, "response_data": {"text": "Dạ mẫu đen còn ạ"}}

    async def fake_send_facebook_reply(*, recipient_id, message_text, reply_to_mid, image_urls=None):
        sent["recipient_id"] = recipient_id
        sent["message_text"] = message_text
        sent["reply_to_mid"] = reply_to_mid
        return {"ok": True}

    monkeypatch.setattr(version_service, "get_ai_version_text_history_items", fake_history)
    monkeypatch.setattr(fw, "_get_or_create_sender_conversation", fake_get_or_create_sender_conversation)
    monkeypatch.setattr(fw, "_reload_conversation_for_pause_check", fake_reload)
    monkeypatch.setattr(fw, "_ensure_sender_initialized", fake_ensure_sender_initialized)
    monkeypatch.setattr(fw, "_post_ai_chat_with_retry", fake_post_ai_chat_with_retry)
    monkeypatch.setattr(fw, "_send_facebook_reply", fake_send_facebook_reply)
    monkeypatch.setattr(fw, "_save_forwarded_messages", AsyncMock())

    result = asyncio.run(fw._run_ai_forward_and_reply(latest))

    assert result["ok"] is True
    assert sent["message_text"] == "Dạ mẫu đen còn ạ"
    assert conversation.version == "1.1"
    assert [event[0] for event in events] == ["init", "post"]


def test_run_ai_forward_and_reply_updates_handover_status_when_ai_reply_matches(monkeypatch):
    latest = {
        "sender_id": "fb_user_1",
        "message_mid": "m_001",
        "page_id": "page_1",
        "text": "toi can nguoi ho tro",
    }

    class _Conversation:
        def __init__(self):
            self.id = "conv-1"
            self.status = fw.ConversationStatus.NEW

    sent: dict = {}
    conversation = _Conversation()

    async def fake_get_or_create_sender_conversation(_latest):
        return conversation

    async def fake_post_ai_chat_with_retry(*, payload, sender_id, message_mid, purpose):
        return {
            "ok": True,
            "response_data": {
                "text": "Dạ em chuyển sale hỗ trợ anh/chị chi tiết hơn ạ.",
            },
        }

    async def fake_send_facebook_reply(*, recipient_id, message_text, reply_to_mid, image_urls=None):
        sent["message_text"] = message_text
        return {"ok": True}

    update_mock = AsyncMock(return_value=SimpleNamespace(id="conv-1", status=fw.ConversationStatus.HANDOVER))

    monkeypatch.setattr(fw, "_get_or_create_sender_conversation", fake_get_or_create_sender_conversation)
    monkeypatch.setattr(fw, "_ensure_sender_initialized", AsyncMock(return_value={"ok": True}))
    monkeypatch.setattr(fw, "_post_ai_chat_with_retry", fake_post_ai_chat_with_retry)
    monkeypatch.setattr(fw, "_send_facebook_reply", fake_send_facebook_reply)
    monkeypatch.setattr(fw, "_save_forwarded_messages", AsyncMock())
    monkeypatch.setattr(fw, "update_conversation_crud_service", update_mock)

    result = asyncio.run(fw._run_ai_forward_and_reply(latest))

    assert result["ok"] is True
    assert sent["message_text"] == "Dạ em chuyển sale hỗ trợ anh/chị chi tiết hơn ạ."
    assert result["handover_detection"]["detected"] is True
    assert result["handover_status_update"] == {
        "updated": True,
        "conversation_id": "conv-1",
        "status": "handover",
    }
    assert conversation.status == fw.ConversationStatus.HANDOVER
    update_mock.assert_awaited_once_with("conv-1", status=fw.ConversationStatus.HANDOVER)


def test_run_ai_forward_and_reply_does_not_update_status_when_ai_reply_does_not_match(monkeypatch):
    latest = {
        "sender_id": "fb_user_1",
        "message_mid": "m_001",
        "page_id": "page_1",
        "text": "xin chao",
    }

    class _Conversation:
        id = "conv-1"

    async def fake_post_ai_chat_with_retry(*, payload, sender_id, message_mid, purpose):
        return {"ok": True, "response_data": {"text": "Dạ em tư vấn size cho chị ạ."}}

    async def should_not_update(*args, **kwargs):  # pragma: no cover - defensive
        raise AssertionError("status update must not run when handover is not detected")

    monkeypatch.setattr(fw, "_get_or_create_sender_conversation", AsyncMock(return_value=_Conversation()))
    monkeypatch.setattr(fw, "_ensure_sender_initialized", AsyncMock(return_value={"ok": True}))
    monkeypatch.setattr(fw, "_post_ai_chat_with_retry", fake_post_ai_chat_with_retry)
    monkeypatch.setattr(fw, "_send_facebook_reply", AsyncMock(return_value={"ok": True}))
    monkeypatch.setattr(fw, "_save_forwarded_messages", AsyncMock())
    monkeypatch.setattr(fw, "update_conversation_crud_service", should_not_update)

    result = asyncio.run(fw._run_ai_forward_and_reply(latest))

    assert result["ok"] is True
    assert result["handover_detection"]["detected"] is False
    assert result["handover_status_update"]["reason"] == "handover_not_detected"


def test_run_ai_forward_and_reply_keeps_reply_when_handover_status_update_fails(monkeypatch):
    latest = {
        "sender_id": "fb_user_1",
        "message_mid": "m_001",
        "page_id": "page_1",
        "text": "toi can nguoi ho tro",
    }

    class _Conversation:
        id = "conv-1"

    async def fake_post_ai_chat_with_retry(*, payload, sender_id, message_mid, purpose):
        return {"ok": True, "response_data": {"text": "Dạ em chuyển xử lý cho anh/chị ạ."}}

    update_mock = AsyncMock(side_effect=RuntimeError("db down"))
    send_mock = AsyncMock(return_value={"ok": True})

    monkeypatch.setattr(fw, "_get_or_create_sender_conversation", AsyncMock(return_value=_Conversation()))
    monkeypatch.setattr(fw, "_ensure_sender_initialized", AsyncMock(return_value={"ok": True}))
    monkeypatch.setattr(fw, "_post_ai_chat_with_retry", fake_post_ai_chat_with_retry)
    monkeypatch.setattr(fw, "_send_facebook_reply", send_mock)
    monkeypatch.setattr(fw, "_save_forwarded_messages", AsyncMock())
    monkeypatch.setattr(fw, "update_conversation_crud_service", update_mock)

    result = asyncio.run(fw._run_ai_forward_and_reply(latest))

    assert result["ok"] is True
    assert result["handover_detection"]["detected"] is True
    assert result["handover_status_update"]["reason"] == "handover_status_update_failed"
    send_mock.assert_awaited_once()


def test_update_handover_conversation_status_skips_missing_conversation_id(monkeypatch):
    class _Conversation:
        id = ""

    async def should_not_update(*args, **kwargs):  # pragma: no cover - defensive
        raise AssertionError("status update must not run without conversation_id")

    monkeypatch.setattr(fw, "update_conversation_crud_service", should_not_update)

    result = asyncio.run(
        fw._update_handover_conversation_status(
            conversation=_Conversation(),
            handover_detection={
                "detected": True,
                "reason": "ai_reply_handover_keyword",
                "matched_pattern": "em chuyen sale",
            },
        )
    )

    assert result == {"updated": False, "reason": "handover_missing_conversation_id"}


def test_update_handover_conversation_status_handles_missing_conversation(monkeypatch):
    class _Conversation:
        id = "missing-conv"

    update_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(fw, "update_conversation_crud_service", update_mock)

    result = asyncio.run(
        fw._update_handover_conversation_status(
            conversation=_Conversation(),
            handover_detection={
                "detected": True,
                "reason": "ai_reply_handover_keyword",
                "matched_pattern": "em chuyen sale",
            },
        )
    )

    assert result == {"updated": False, "reason": "handover_conversation_not_found"}
    update_mock.assert_awaited_once_with("missing-conv", status=fw.ConversationStatus.HANDOVER)


def test_prepare_facebook_reply_looks_up_drive_images_from_brain_text(monkeypatch):
    captured = {}

    class _Image:
        def __init__(self, image_url):
            self.imageUrl = image_url

    class _Folder:
        error = None

        def __init__(self, images):
            self.images = images

    class _FakeDriveService:
        async def lookup_folder_images(self, urls):
            captured["urls"] = urls
            return [
                _Folder(
                    [
                        _Image("https://lh3.googleusercontent.com/d/image_1"),
                        _Image("https://lh3.googleusercontent.com/d/image_2"),
                        _Image("https://lh3.googleusercontent.com/d/image_3"),
                        _Image("https://lh3.googleusercontent.com/d/image_4"),
                    ]
                )
            ]

    monkeypatch.setattr(fw, "GoogleDriveImageService", _FakeDriveService)

    brain_message = (
        "Dạ em có thể gửi chị **link lookbook** của mẫu **W2651713** để mình xem ạ:  \n"
        "https://drive.google.com/drive/folders/16lg-E8eT7eeiYtv-X80BgD71AYHvbGNJ 💕  \n"
        "\n"
        "Chị muốn em tư vấn luôn **size** cho mình không ạ?"
    )

    result = asyncio.run(
        fw._prepare_facebook_reply_from_ai_response(
            response_data={"text": brain_message},
            assistant_message=brain_message,
        )
    )

    assert result.text == (
        "Dạ em có thể gửi chị **link lookbook** của mẫu **W2651713** để mình xem ạ:\n"
        "\n"
        "Chị muốn em tư vấn luôn **size** cho mình không ạ?"
    )
    assert captured["urls"] == [
        "https://drive.google.com/drive/folders/16lg-E8eT7eeiYtv-X80BgD71AYHvbGNJ"
    ]
    assert result.image_urls == [
        "https://lh3.googleusercontent.com/d/image_1",
        "https://lh3.googleusercontent.com/d/image_2",
        "https://lh3.googleusercontent.com/d/image_3",
    ]


def test_prepare_facebook_reply_uses_structured_drive_urls_without_text_link(monkeypatch):
    captured = {}

    class _Image:
        imageUrl = "https://lh3.googleusercontent.com/d/image_1"

    class _Folder:
        error = None
        images = [_Image()]

    class _FakeDriveService:
        async def lookup_folder_images(self, urls):
            captured["urls"] = urls
            return [_Folder()]

    monkeypatch.setattr(fw, "GoogleDriveImageService", _FakeDriveService)

    result = asyncio.run(
        fw._prepare_facebook_reply_from_ai_response(
            response_data={
                "text": "Dạ em gửi ảnh mẫu này cho chị ạ.",
                "drive_folder_urls": [
                    "https://drive.google.com/drive/folders/folder_1",
                ],
                "image_limit": 1,
            },
            assistant_message="Dạ em gửi ảnh mẫu này cho chị ạ.",
        )
    )

    assert result.text == "Dạ em gửi ảnh mẫu này cho chị ạ."
    assert captured["urls"] == ["https://drive.google.com/drive/folders/folder_1"]
    assert result.image_urls == ["https://lh3.googleusercontent.com/d/image_1"]


def test_prepare_facebook_reply_does_not_lookup_drive_when_no_link(monkeypatch):
    class _ShouldNotCallDriveService:
        async def lookup_folder_images(self, urls):  # pragma: no cover - defensive
            raise AssertionError("Drive lookup must not run when Brain returns no Drive link")

    monkeypatch.setattr(fw, "GoogleDriveImageService", _ShouldNotCallDriveService)

    result = asyncio.run(
        fw._prepare_facebook_reply_from_ai_response(
            response_data={"text": "Dạ em tư vấn size cho chị ạ."},
            assistant_message="Dạ em tư vấn size cho chị ạ.",
        )
    )

    assert result.text == "Dạ em tư vấn size cho chị ạ."
    assert result.drive_folder_urls == []
    assert result.image_urls == []


def test_run_ai_forward_and_reply_suppresses_send_when_paused_before_send(monkeypatch):
    latest = {
        "sender_id": "fb_user_1",
        "message_mid": "m_001",
        "page_id": "page_1",
        "text": "xin chao",
    }

    active_conversation = _FakeConversation(initialized=True)
    paused_conversation = _FakeConversation(
        initialized=True,
        paused_until=now_vn() + timedelta(minutes=5),
    )

    async def fake_post_ai_chat_with_retry(*, payload, sender_id, message_mid, purpose):
        return {
            "ok": True,
            "response_data": {"choices": [{"message": {"content": "Dạ chào bạn"}}]},
        }

    async def should_not_send(**kwargs):  # pragma: no cover - defensive
        raise AssertionError("bot reply must not be sent after admin takeover")

    async def should_not_save(**kwargs):  # pragma: no cover - defensive
        raise AssertionError("suppressed bot reply must not be persisted as bot message")

    monkeypatch.setattr(fw, "_get_or_create_sender_conversation", AsyncMock(return_value=active_conversation))
    monkeypatch.setattr(fw, "_ensure_sender_initialized", AsyncMock(return_value={"ok": True}))
    monkeypatch.setattr(fw, "_post_ai_chat_with_retry", fake_post_ai_chat_with_retry)
    monkeypatch.setattr(fw, "_reload_conversation_for_pause_check", AsyncMock(return_value=paused_conversation))
    monkeypatch.setattr(fw, "_send_facebook_reply", should_not_send)
    monkeypatch.setattr(fw, "_save_forwarded_messages", should_not_save)

    result = asyncio.run(fw._run_ai_forward_and_reply(latest))

    assert result["ok"] is False
    assert result["reason"] == "conversation_paused_before_send"


def test_ensure_customer_message_can_enqueue_blocks_paused_conversation(monkeypatch):
    paused_conversation = _FakeConversation(
        initialized=True,
        paused_until=now_vn() + timedelta(minutes=5),
    )
    monkeypatch.setattr(fw, "_get_or_create_sender_conversation", AsyncMock(return_value=paused_conversation))

    result = asyncio.run(
        fw._ensure_customer_message_can_enqueue(
            {"sender_id": "fb_user_1", "message_mid": "m_001"}
        )
    )

    assert result["ok"] is False
    assert result["reason"] == "conversation_paused_by_admin"


def test_ensure_customer_message_can_enqueue_resumes_expired_pause(monkeypatch):
    expired_conversation = _FakeConversation(
        initialized=True,
        paused_until=now_vn() - timedelta(minutes=1),
    )
    expired_conversation.bot_paused_at = now_vn() - timedelta(minutes=11)
    expired_conversation.bot_paused_reason = "admin_message"
    expired_conversation.bot_paused_by = "page-1"
    monkeypatch.setattr(fw, "_get_or_create_sender_conversation", AsyncMock(return_value=expired_conversation))

    result = asyncio.run(
        fw._ensure_customer_message_can_enqueue(
            {"sender_id": "fb_user_1", "message_mid": "m_001"}
        )
    )

    assert result["ok"] is True
    assert result["resumed"] is True
    assert expired_conversation.bot_paused_until is None
    assert expired_conversation.bot_paused_at is None
    assert expired_conversation.bot_paused_reason is None
    assert expired_conversation.bot_paused_by is None
    assert expired_conversation.save_called == 1


def test_save_admin_message_persists_staff_role(monkeypatch):
    inserted_messages = []

    class _MessageMid:
        def __eq__(self, other):
            return ("message_mid", other)

    class _FakeMessage:
        message_mid = _MessageMid()

        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.id = "admin-msg-1"

        @classmethod
        async def find_one(cls, query):
            return None

        async def insert(self):
            inserted_messages.append(self)

    conversation = _FakeConversation(initialized=True)
    monkeypatch.setattr(fw, "Message", _FakeMessage)

    result = asyncio.run(
        fw._save_admin_message(
            conversation,
            {
                "message_mid": "m_admin",
                "text": "hi bạn",
                "page_id": "page-1",
                "recipient_id": "fb_user_1",
                "metadata": "",
                "app_id": 263902037430900,
                "timestamp": 1776758143079,
            },
        )
    )

    assert result["saved"] is True
    assert inserted_messages[0].role == "staff"
    assert inserted_messages[0].content == "hi bạn"
    assert inserted_messages[0].meta["source"] == "facebook_webhook_admin_echo"
    assert inserted_messages[0].meta["customer_id"] == "fb_user_1"


def test_receive_webhook_admin_echo_pauses_and_does_not_enqueue(monkeypatch):
    payload = {
        "object": "page",
        "entry": [
            {
                "id": "page-1",
                "messaging": [
                    {
                        "sender": {"id": "page-1"},
                        "recipient": {"id": "fb_user_1"},
                        "timestamp": 1776758143079,
                        "message": {
                            "mid": "m_admin",
                            "is_echo": True,
                            "text": "hi",
                            "app_id": 263902037430900,
                        },
                    }
                ],
            }
        ],
    }
    admin_handler = AsyncMock(
        return_value={
            "conversation_id": "conv-1",
            "buffer_result": {"cancelled": False, "message_count": 0},
        }
    )

    async def should_not_enqueue(_latest):  # pragma: no cover - defensive
        raise AssertionError("admin echo must not be enqueued to AI")

    monkeypatch.setattr(fw.settings, "fb_page_id", "page-1")
    monkeypatch.setattr(fw, "_handle_admin_message", admin_handler)
    monkeypatch.setattr(fw, "_enqueue_sender_message", should_not_enqueue)

    result = asyncio.run(fw.receive_webhook(_FakeRequest(payload)))

    assert result["status"] == "ignored"
    assert result["ignored_messages"][0]["reason"] == "admin_message_paused_conversation"
    admin_handler.assert_awaited_once()


def test_receive_webhook_bot_echo_ignores_without_admin_pause(monkeypatch):
    payload = {
        "object": "page",
        "entry": [
            {
                "id": "page-1",
                "messaging": [
                    {
                        "sender": {"id": "page-1"},
                        "recipient": {"id": "fb_user_1"},
                        "timestamp": 1776758197478,
                        "message": {
                            "mid": "m_bot",
                            "is_echo": True,
                            "text": "bot reply",
                            "metadata": "source_mid:m_customer",
                        },
                    }
                ],
            }
        ],
    }

    async def should_not_pause(_latest):  # pragma: no cover - defensive
        raise AssertionError("bot echo must not pause the conversation")

    async def should_not_enqueue(_latest):  # pragma: no cover - defensive
        raise AssertionError("bot echo must not be enqueued to AI")

    monkeypatch.setattr(fw.settings, "fb_page_id", "page-1")
    monkeypatch.setattr(fw, "_handle_admin_message", should_not_pause)
    monkeypatch.setattr(fw, "_enqueue_sender_message", should_not_enqueue)

    result = asyncio.run(fw.receive_webhook(_FakeRequest(payload)))

    assert result["status"] == "ignored"
    assert result["ignored_messages"][0]["reason"] == "bot_echo"


def test_receive_webhook_customer_message_enqueues_when_active(monkeypatch):
    payload = {
        "object": "page",
        "entry": [
            {
                "id": "page-1",
                "messaging": [
                    {
                        "sender": {"id": "fb_user_1"},
                        "recipient": {"id": "page-1"},
                        "timestamp": 1776758172907,
                        "message": {"mid": "m_customer", "text": "hello"},
                    }
                ],
            }
        ],
    }

    class _MessageMid:
        def __eq__(self, other):
            return ("message_mid", other)

    class _FakeMessage:
        message_mid = _MessageMid()

        @classmethod
        async def find_one(cls, query):
            return None

    enqueue_mock = AsyncMock(return_value={"buffer_size": 1, "wait_seconds": 15})
    monkeypatch.setattr(fw.settings, "fb_page_id", "page-1")
    monkeypatch.setattr(
        fw,
        "_fetch_participant_names_from_conversations",
        AsyncMock(return_value={"sender_name": None, "page_name": "MediaX AI"}),
    )
    monkeypatch.setattr(fw, "_fetch_sender_name_direct", AsyncMock(return_value=None))
    monkeypatch.setattr(fw, "Message", _FakeMessage)
    monkeypatch.setattr(
        fw,
        "_ensure_customer_message_can_enqueue",
        AsyncMock(return_value={"ok": True, "conversation_id": "conv-1", "resumed": False}),
    )
    monkeypatch.setattr(fw, "_enqueue_sender_message", enqueue_mock)

    result = asyncio.run(fw.receive_webhook(_FakeRequest(payload)))

    assert result["status"] == "QUEUED"
    assert result["queued_count"] == 1
    assert result["queued_messages"][0]["message_mid"] == "m_customer"
    enqueue_mock.assert_awaited_once()


def test_cancel_sender_buffer_cancels_task_and_clears_inflight_mids():
    class _FakeTask:
        def __init__(self):
            self.cancelled = False

        def done(self):
            return False

        def cancel(self):
            self.cancelled = True

    task = _FakeTask()
    sender_id = "fb_user_1"
    fw._sender_buffers[sender_id] = {
        "messages": [{"message_mid": "m_001"}, {"message_mid": "m_002"}],
        "task": task,
    }
    fw._processing_message_mids.update({"m_001", "m_002"})

    try:
        result = fw._cancel_sender_buffer(sender_id)
    finally:
        fw._sender_buffers.pop(sender_id, None)
        fw._processing_message_mids.discard("m_001")
        fw._processing_message_mids.discard("m_002")

    assert result["cancelled"] is True
    assert result["message_count"] == 2
    assert task.cancelled is True
    assert "m_001" not in fw._processing_message_mids
    assert "m_002" not in fw._processing_message_mids


def test_process_sender_buffer_finalizes_pause_suppressed_result(monkeypatch):
    sender_id = "fb_user_1"
    message_mid = "m_001"
    fw._sender_buffers[sender_id] = {
        "messages": [{"sender_id": sender_id, "message_mid": message_mid, "text": "hello"}],
        "task": None,
    }
    fw._processing_message_mids.add(message_mid)
    monkeypatch.setattr(
        fw,
        "_run_ai_forward_and_reply",
        AsyncMock(return_value={"ok": False, "reason": "conversation_paused_before_send"}),
    )

    try:
        asyncio.run(fw._process_sender_buffer_after_delay(sender_id, delay_seconds=0))
        assert sender_id not in fw._sender_buffers
        assert message_mid not in fw._processing_message_mids
    finally:
        fw._sender_buffers.pop(sender_id, None)
        fw._processing_message_mids.discard(message_mid)


def test_has_non_retryable_facebook_error_detects_nested_send_result():
    assert fw._has_non_retryable_facebook_error(
        {
            "image_result": {
                "bulk_result": {
                    "reason": "facebook_auth_error",
                    "non_retryable": True,
                }
            }
        }
    ) is True


def test_process_sender_buffer_drops_non_retryable_facebook_reply_failure(monkeypatch):
    sender_id = "fb_user_1"
    message_mid = "m_001"
    fw._sender_buffers[sender_id] = {
        "messages": [{"sender_id": sender_id, "message_mid": message_mid, "text": "hello"}],
        "task": None,
    }
    fw._processing_message_mids.add(message_mid)
    monkeypatch.setattr(
        fw,
        "_run_ai_forward_and_reply",
        AsyncMock(
            return_value={
                "ok": False,
                "reason": "facebook_reply_non_retryable",
                "non_retryable": True,
                "send_result": {"reason": "facebook_auth_error", "non_retryable": True},
            }
        ),
    )

    try:
        asyncio.run(fw._process_sender_buffer_after_delay(sender_id, delay_seconds=0))
        assert sender_id not in fw._sender_buffers
        assert message_mid not in fw._processing_message_mids
    finally:
        fw._sender_buffers.pop(sender_id, None)
        fw._processing_message_mids.discard(message_mid)


def test_ensure_sender_initialized_skips_when_already_initialized(monkeypatch):
    conversation = _FakeConversation(initialized=True)

    async def should_not_call_post(**kwargs):  # pragma: no cover - defensive
        raise AssertionError("init request must not be sent when already initialized")

    monkeypatch.setattr(fw, "_post_ai_chat_with_retry", should_not_call_post)

    result = asyncio.run(
        fw._ensure_sender_initialized(
            latest={"sender_id": "fb_user_1", "message_mid": "m_123"},
            conversation=conversation,
        )
    )

    assert result["ok"] is True
    assert result["reason"] == "already_initialized"
    assert conversation.save_called == 0


def test_ensure_sender_initialized_calls_init_once_and_sets_flag(monkeypatch):
    conversation = _FakeConversation(initialized=False)
    captured = {}

    async def fake_post_ai_chat_with_retry(*, payload, sender_id, message_mid, purpose):
        captured["payload"] = payload
        captured["sender_id"] = sender_id
        captured["message_mid"] = message_mid
        captured["purpose"] = purpose
        return {"ok": True, "status_code": 200, "response_data": {"ok": True}}

    monkeypatch.setattr(fw, "_post_ai_chat_with_retry", fake_post_ai_chat_with_retry)

    result = asyncio.run(
        fw._ensure_sender_initialized(
            latest={"sender_id": "fb_user_2", "message_mid": "m_456"},
            conversation=conversation,
        )
    )

    assert result["ok"] is True
    assert result["reason"] == "initialized_now"
    assert conversation.fb_ai_initialized is True
    assert conversation.save_called == 1
    assert captured["sender_id"] == "fb_user_2"
    assert captured["message_mid"] == "m_456"
    assert captured["purpose"] == "init"
    assert captured["payload"] == {
        "user": "fb_user_2",
        "messages": [
            {
                "role": "user",
                "content": fw.FB_AI_INIT_MESSAGE,
            }
        ],
        "stream": False,
    }


def test_ensure_sender_initialized_uses_ai_user_override(monkeypatch):
    conversation = _FakeConversation(initialized=False)
    captured = {}

    async def fake_post_ai_chat_with_retry(*, payload, sender_id, message_mid, purpose):
        captured["payload"] = payload
        captured["sender_id"] = sender_id
        captured["purpose"] = purpose
        return {"ok": True, "status_code": 200, "response_data": {"ok": True}}

    monkeypatch.setattr(fw, "_post_ai_chat_with_retry", fake_post_ai_chat_with_retry)

    result = asyncio.run(
        fw._ensure_sender_initialized(
            latest={"sender_id": "fb_user_2", "message_mid": "m_456"},
            conversation=conversation,
            ai_user="fb_user_2:v1.1",
        )
    )

    assert result["ok"] is True
    assert captured["sender_id"] == "fb_user_2:v1.1"
    assert captured["purpose"] == "init"
    assert captured["payload"]["user"] == "fb_user_2:v1.1"


def test_prepare_versioned_ai_session_resets_then_initializes(monkeypatch):
    conversation = _FakeConversation(initialized=True)
    events = []

    async def fake_reset(target_conversation):
        events.append(("reset", target_conversation.fb_ai_initialized))
        target_conversation.fb_ai_initialized = False
        target_conversation.fb_ai_initialized_at = None

    async def fake_ensure_sender_initialized(*, latest, conversation, ai_user=None):
        events.append(("init", conversation.fb_ai_initialized, ai_user))
        return {"ok": True, "reason": "initialized_now"}

    monkeypatch.setattr(fw, "reset_ai_initialization_for_version_session", fake_reset)
    monkeypatch.setattr(fw, "_ensure_sender_initialized", fake_ensure_sender_initialized)

    result = asyncio.run(
        fw._prepare_versioned_ai_session(
            latest={"sender_id": "fb_user_2", "message_mid": "m_456"},
            conversation=conversation,
            target_version="1.1",
        )
    )

    assert result["ok"] is True
    assert result["ai_user"] == "fb_user_2:v1.1"
    assert result["version"] == "1.1"
    assert events == [
        ("reset", True),
        ("init", False, "fb_user_2:v1.1"),
    ]


def test_prepare_versioned_ai_session_stops_when_reset_fails(monkeypatch):
    conversation = _FakeConversation(initialized=True)
    ensure_mock = AsyncMock(return_value={"ok": True})

    async def fake_reset(target_conversation):
        raise RuntimeError("db down")

    monkeypatch.setattr(fw, "reset_ai_initialization_for_version_session", fake_reset)
    monkeypatch.setattr(fw, "_ensure_sender_initialized", ensure_mock)

    result = asyncio.run(
        fw._prepare_versioned_ai_session(
            latest={"sender_id": "fb_user_2", "message_mid": "m_456"},
            conversation=conversation,
            target_version="1.1",
        )
    )

    assert result["ok"] is False
    assert result["reason"] == "ai_version_init_state_reset_failed"
    assert result["ai_user"] == "fb_user_2:v1.1"
    ensure_mock.assert_not_awaited()
