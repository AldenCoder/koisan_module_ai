import asyncio
import json

import pytest

from app.services import pancake_message_service as pms


def _set_pancake_page_tokens(monkeypatch, mapping=None):
    tokens = {"page-1": "token-1", "page-2": "token-2"} if mapping is None else mapping
    raw_tokens = tokens if isinstance(tokens, str) else json.dumps(tokens)
    monkeypatch.setattr(pms.settings, "pancake_page_access_tokens_by_page_id", raw_tokens, raising=False)


def test_sanitize_pancake_outgoing_message_removes_all_asterisks():
    assert (
        pms.sanitize_pancake_outgoing_message(
            "**S2650547**\n- **Gia**: **339.000**\nMau **den, tim**"
        )
        == "S2650547\n- Gia: 339.000\nMau den, tim"
    )


def test_sanitize_pancake_outgoing_message_removes_internal_edit_failed_artifact():
    message = (
        "Da em da nho roi a.\n\n"
        "\u26a0\ufe0f \U0001f4dd Edit: `in /data/workspace/memory/2026-06-24.md` failed"
    )

    assert pms.sanitize_pancake_outgoing_message(message) == "Da em da nho roi a."


def test_sanitize_pancake_outgoing_message_truncates_any_text_after_warning_icon():
    message = "Da em da nho roi a. \u26a0\ufe0f Tool output changed format"

    assert pms.sanitize_pancake_outgoing_message(message) == "Da em da nho roi a."


def test_build_pancake_reply_payload_uses_reply_inbox_action():
    assert pms.build_pancake_reply_payload(message="Xin chào") == {
        "action": "reply_inbox",
        "message": "Xin chào",
    }


def test_build_pancake_reply_payload_removes_ai_markdown_bold_asterisks():
    assert pms.build_pancake_reply_payload(
        message="Da chi, mau **S2650547** la **set vest** a."
    ) == {
        "action": "reply_inbox",
        "message": "Da chi, mau S2650547 la set vest a.",
    }


def test_build_pancake_comment_reply_payload_uses_comment_contract():
    assert pms.build_pancake_comment_reply_payload(
        comment_message_id="comment-1",
        message="Xin chào",
    ) == {
        "action": "reply_comment",
        "message_id": "comment-1",
        "message": "Xin chào",
    }


def test_build_pancake_comment_reply_payload_removes_ai_markdown_bold_asterisks():
    assert pms.build_pancake_comment_reply_payload(
        comment_message_id="comment-1",
        message="- **Chat vai**: **Cheo Han cao cap**",
    ) == {
        "action": "reply_comment",
        "message_id": "comment-1",
        "message": "- Chat vai: Cheo Han cao cap",
    }


def test_build_pancake_comment_content_ids_payload_uses_comment_contract():
    assert pms.build_pancake_comment_content_ids_payload(
        comment_message_id="comment-1",
        content_ids=["content-1"],
    ) == {
        "action": "reply_comment",
        "message_id": "comment-1",
        "content_ids": ["content-1"],
    }


def test_build_pancake_messages_api_url_includes_page_and_conversation():
    assert pms.build_pancake_messages_api_url(page_id="page-1", conversation_id="conv-1") == (
        "https://pages.fm/api/public_api/v1/pages/page-1/conversations/conv-1/messages"
    )


def test_build_pancake_upload_contents_api_url_includes_page():
    assert pms.build_pancake_upload_contents_api_url(page_id="page-1") == (
        "https://pages.fm/api/public_api/v1/pages/page-1/upload_contents"
    )


def test_build_pancake_content_ids_payload_uses_reply_inbox_action():
    assert pms.build_pancake_content_ids_payload(content_ids=["content-1", "content-2"]) == {
        "action": "reply_inbox",
        "content_ids": ["content-1", "content-2"],
    }


def test_suppress_httpx_info_logs_restores_logger_level():
    httpx_logger = pms.logging.getLogger("httpx")
    original_level = httpx_logger.level

    try:
        httpx_logger.setLevel(pms.logging.INFO)
        with pms._suppress_httpx_info_logs():
            assert httpx_logger.level == pms.logging.WARNING
        assert httpx_logger.level == pms.logging.INFO
    finally:
        httpx_logger.setLevel(original_level)


def test_get_pancake_page_access_tokens_by_page_id_parses_json(monkeypatch):
    _set_pancake_page_tokens(
        monkeypatch,
        {
            " page-1 ": " token-1 ",
            "": "ignored-token",
            "page-empty": "",
            "page-2": "token-2",
        },
    )

    assert pms._get_pancake_page_access_tokens_by_page_id() == {
        "page-1": "token-1",
        "page-2": "token-2",
    }


def test_get_pancake_page_access_tokens_by_page_id_rejects_missing_env(monkeypatch):
    monkeypatch.setattr(pms.settings, "pancake_page_access_tokens_by_page_id", "", raising=False)

    try:
        pms._get_pancake_page_access_tokens_by_page_id()
    except pms.PancakePageAccessTokenConfigError as exc:
        assert exc.reason == pms.PANCAKE_MISSING_PAGE_ACCESS_TOKENS_REASON
    else:  # pragma: no cover - defensive
        raise AssertionError("missing token mapping should raise")


def test_get_pancake_page_access_tokens_by_page_id_rejects_invalid_json(monkeypatch):
    monkeypatch.setattr(pms.settings, "pancake_page_access_tokens_by_page_id", '{"page-1":"token-1",}', raising=False)

    try:
        pms._get_pancake_page_access_tokens_by_page_id()
    except pms.PancakePageAccessTokenConfigError as exc:
        assert exc.reason == pms.PANCAKE_INVALID_PAGE_ACCESS_TOKENS_REASON
    else:  # pragma: no cover - defensive
        raise AssertionError("invalid token mapping should raise")


def test_get_pancake_page_access_tokens_by_page_id_rejects_non_object(monkeypatch):
    monkeypatch.setattr(pms.settings, "pancake_page_access_tokens_by_page_id", '["token-1"]', raising=False)

    try:
        pms._get_pancake_page_access_tokens_by_page_id()
    except pms.PancakePageAccessTokenConfigError as exc:
        assert exc.reason == pms.PANCAKE_INVALID_PAGE_ACCESS_TOKENS_REASON
    else:  # pragma: no cover - defensive
        raise AssertionError("non-object token mapping should raise")


def test_get_pancake_page_access_tokens_by_page_id_rejects_json_string(monkeypatch):
    monkeypatch.setattr(pms.settings, "pancake_page_access_tokens_by_page_id", '"token-1"', raising=False)

    try:
        pms._get_pancake_page_access_tokens_by_page_id()
    except pms.PancakePageAccessTokenConfigError as exc:
        assert exc.reason == pms.PANCAKE_INVALID_PAGE_ACCESS_TOKENS_REASON
    else:  # pragma: no cover - defensive
        raise AssertionError("JSON string token mapping should raise")


def test_get_pancake_page_access_tokens_by_page_id_rejects_non_string_values(monkeypatch):
    _set_pancake_page_tokens(monkeypatch, {"page-1": 123})

    try:
        pms._get_pancake_page_access_tokens_by_page_id()
    except pms.PancakePageAccessTokenConfigError as exc:
        assert exc.reason == pms.PANCAKE_INVALID_PAGE_ACCESS_TOKENS_REASON
    else:  # pragma: no cover - defensive
        raise AssertionError("non-string token mapping value should raise")


def test_get_pancake_page_access_token_for_page_does_not_fallback_to_single_token(monkeypatch):
    _set_pancake_page_tokens(monkeypatch, {"other-page": "other-token"})
    monkeypatch.setattr(pms.settings, "pancake_page_access_token", "fallback-token", raising=False)

    try:
        pms._get_pancake_page_access_token_for_page(page_id="page-1")
    except pms.PancakePageAccessTokenConfigError as exc:
        assert exc.reason == pms.PANCAKE_MISSING_PAGE_ACCESS_TOKEN_FOR_PAGE_REASON
        assert exc.page_id == "page-1"
    else:  # pragma: no cover - defensive
        raise AssertionError("missing page token should raise")


def test_get_pancake_page_access_token_for_page_requires_page_id(monkeypatch):
    _set_pancake_page_tokens(monkeypatch)

    try:
        pms._get_pancake_page_access_token_for_page(page_id=" ")
    except pms.PancakePageAccessTokenConfigError as exc:
        assert exc.reason == "missing_page_id"
    else:  # pragma: no cover - defensive
        raise AssertionError("missing page id should raise")


def test_send_pancake_reply_requires_page_token(monkeypatch):
    _set_pancake_page_tokens(monkeypatch, {"other-page": "other-token"})
    monkeypatch.setattr(pms.settings, "pancake_page_access_token", "fallback-token", raising=False)

    result = asyncio.run(
        pms.send_pancake_reply(
            page_id="page-1",
            conversation_id="conv-1",
            message="Xin chào",
        )
    )

    assert result == {
        "ok": False,
        "reason": pms.PANCAKE_MISSING_PAGE_ACCESS_TOKEN_FOR_PAGE_REASON,
        "non_retryable": True,
        "page_id": "page-1",
    }


def test_send_pancake_reply_missing_page_token_logs_context_without_token(monkeypatch, caplog):
    _set_pancake_page_tokens(monkeypatch, {"other-page": "secret-token"})
    monkeypatch.setattr(pms.settings, "pancake_page_access_token", "fallback-secret", raising=False)

    with caplog.at_level(pms.logging.WARNING):
        result = asyncio.run(
            pms.send_pancake_reply(
                page_id="page-1",
                conversation_id="conv-1",
                message="Xin chào",
            )
        )

    assert result["reason"] == pms.PANCAKE_MISSING_PAGE_ACCESS_TOKEN_FOR_PAGE_REASON
    assert "page-1" in caplog.text
    assert "conv-1" in caplog.text
    assert pms.PANCAKE_MISSING_PAGE_ACCESS_TOKEN_FOR_PAGE_REASON in caplog.text
    assert "secret-token" not in caplog.text
    assert "fallback-secret" not in caplog.text


def test_send_pancake_reply_success(monkeypatch):
    calls = []
    _set_pancake_page_tokens(monkeypatch)

    async def fake_post(*, page_access_token, page_id, conversation_id, payload, timeout):
        calls.append(
            {
                "page_access_token": page_access_token,
                "page_id": page_id,
                "conversation_id": conversation_id,
                "payload": payload,
                "timeout": timeout,
            }
        )
        return {"ok": True, "status_code": 200, "response_data": {"id": "reply-1"}}

    monkeypatch.setattr(pms, "_post_pancake_reply_payload", fake_post)

    result = asyncio.run(
        pms.send_pancake_reply(
            page_id="page-1",
            conversation_id="conv-1",
            message="Xin chào",
            retry_attempts=3,
        )
    )

    assert result["ok"] is True
    assert result["response_data"] == {"id": "reply-1"}
    assert len(calls) == 1
    assert calls[0]["payload"] == {"action": "reply_inbox", "message": "Xin chào"}
    assert calls[0]["page_access_token"] == "token-1"


def test_send_pancake_reply_removes_asterisks_before_post(monkeypatch):
    calls = []
    _set_pancake_page_tokens(monkeypatch)

    async def fake_post(*, page_access_token, page_id, conversation_id, payload, timeout):
        calls.append(payload)
        return {"ok": True, "status_code": 200, "response_data": {"id": "reply-1"}}

    monkeypatch.setattr(pms, "_post_pancake_reply_payload", fake_post)

    result = asyncio.run(
        pms.send_pancake_reply(
            page_id="page-1",
            conversation_id="conv-1",
            message=" **S2650547** la **set vest cong so** ",
        )
    )

    assert result["ok"] is True
    assert calls == [
        {
            "action": "reply_inbox",
            "message": "S2650547 la set vest cong so",
        }
    ]


def test_send_pancake_reply_rejects_message_empty_after_sanitizing_asterisks(monkeypatch):
    monkeypatch.setattr(
        pms,
        "_get_pancake_page_access_token_for_page",
        lambda **unused: (_ for _ in ()).throw(
            AssertionError("must not lookup token for empty sanitized message")
        ),
    )

    result = asyncio.run(
        pms.send_pancake_reply(
            page_id="page-1",
            conversation_id="conv-1",
            message=" ** ",
        )
    )

    assert result == {
        "ok": False,
        "reason": "missing_reply_message",
        "non_retryable": True,
    }


@pytest.mark.parametrize(
    ("kwargs", "expected_reason"),
    [
        (
            {
                "page_id": " ",
                "conversation_id": "conv-1",
                "comment_message_id": "comment-1",
                "message": "Xin chào",
            },
            "missing_page_id",
        ),
        (
            {
                "page_id": "page-1",
                "conversation_id": " ",
                "comment_message_id": "comment-1",
                "message": "Xin chào",
            },
            "missing_pancake_conversation_id",
        ),
        (
            {
                "page_id": "page-1",
                "conversation_id": "conv-1",
                "comment_message_id": " ",
                "message": "Xin chào",
            },
            "missing_pancake_comment_message_id",
        ),
        (
            {
                "page_id": "page-1",
                "conversation_id": "conv-1",
                "comment_message_id": "comment-1",
                "message": " ",
            },
            "missing_reply_message",
        ),
    ],
)
def test_send_pancake_comment_reply_validates_before_token_lookup(
    monkeypatch,
    kwargs,
    expected_reason,
):
    monkeypatch.setattr(
        pms,
        "_get_pancake_page_access_token_for_page",
        lambda **unused: (_ for _ in ()).throw(
            AssertionError("must not lookup token for invalid input")
        ),
    )
    monkeypatch.setattr(
        pms,
        "_post_pancake_reply_payload",
        lambda **unused: (_ for _ in ()).throw(
            AssertionError("must not call Pancake API for invalid input")
        ),
    )

    result = asyncio.run(pms.send_pancake_comment_reply(**kwargs))

    assert result == {
        "ok": False,
        "reason": expected_reason,
        "non_retryable": True,
    }


def test_send_pancake_comment_reply_requires_page_token(monkeypatch):
    _set_pancake_page_tokens(monkeypatch, {"other-page": "other-token"})

    result = asyncio.run(
        pms.send_pancake_comment_reply(
            page_id="page-1",
            conversation_id="conv-1",
            comment_message_id="comment-1",
            message="Xin chào",
        )
    )

    assert result == {
        "ok": False,
        "reason": pms.PANCAKE_MISSING_PAGE_ACCESS_TOKEN_FOR_PAGE_REASON,
        "non_retryable": True,
        "page_id": "page-1",
    }


def test_send_pancake_comment_reply_rejects_invalid_token_mapping(monkeypatch):
    _set_pancake_page_tokens(monkeypatch, '{"page-1":"token-1",}')

    result = asyncio.run(
        pms.send_pancake_comment_reply(
            page_id="page-1",
            conversation_id="conv-1",
            comment_message_id="comment-1",
            message="Xin chào",
        )
    )

    assert result == {
        "ok": False,
        "reason": pms.PANCAKE_INVALID_PAGE_ACCESS_TOKENS_REASON,
        "non_retryable": True,
        "page_id": "page-1",
    }


def test_send_pancake_comment_reply_success(monkeypatch):
    calls = []
    _set_pancake_page_tokens(monkeypatch)

    async def fake_post(*, page_access_token, page_id, conversation_id, payload, timeout):
        calls.append(
            {
                "page_access_token": page_access_token,
                "page_id": page_id,
                "conversation_id": conversation_id,
                "payload": payload,
                "timeout": timeout,
            }
        )
        return {
            "ok": True,
            "status_code": 200,
            "response_data": {"id": "comment-reply-1"},
        }

    monkeypatch.setattr(pms, "_post_pancake_reply_payload", fake_post)

    result = asyncio.run(
        pms.send_pancake_comment_reply(
            page_id=" page-1 ",
            conversation_id=" conv-1 ",
            comment_message_id=" comment-1 ",
            message=" Xin chào ",
        )
    )

    assert result["ok"] is True
    assert calls == [
        {
            "page_access_token": "token-1",
            "page_id": "page-1",
            "conversation_id": "conv-1",
            "payload": {
                "action": "reply_comment",
                "message_id": "comment-1",
                "message": "Xin chào",
            },
            "timeout": 30.0,
        }
    ]


def test_send_pancake_comment_reply_removes_asterisks_before_post(monkeypatch):
    calls = []
    _set_pancake_page_tokens(monkeypatch)

    async def fake_post(*, page_access_token, page_id, conversation_id, payload, timeout):
        calls.append(payload)
        return {
            "ok": True,
            "status_code": 200,
            "response_data": {"id": "comment-reply-1"},
        }

    monkeypatch.setattr(pms, "_post_pancake_reply_payload", fake_post)

    result = asyncio.run(
        pms.send_pancake_comment_reply(
            page_id="page-1",
            conversation_id="conv-1",
            comment_message_id="comment-1",
            message="**Gia**: **339.000**",
        )
    )

    assert result["ok"] is True
    assert calls == [
        {
            "action": "reply_comment",
            "message_id": "comment-1",
            "message": "Gia: 339.000",
        }
    ]


@pytest.mark.parametrize(
    ("status_code", "reason"),
    [
        (400, "pancake_payload_error"),
        (401, "pancake_auth_error"),
        (403, "pancake_auth_error"),
        (404, "pancake_conversation_not_found"),
    ],
)
def test_send_pancake_comment_reply_does_not_retry_non_retryable_error(
    monkeypatch,
    status_code,
    reason,
):
    calls = []
    sleeps = []
    _set_pancake_page_tokens(monkeypatch)

    async def fake_post(**kwargs):
        calls.append(kwargs)
        return {
            "ok": False,
            "reason": reason,
            "non_retryable": True,
            "status_code": status_code,
        }

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(pms, "_post_pancake_reply_payload", fake_post)
    monkeypatch.setattr(pms.asyncio, "sleep", fake_sleep)

    result = asyncio.run(
        pms.send_pancake_comment_reply(
            page_id="page-1",
            conversation_id="conv-1",
            comment_message_id="comment-1",
            message="Xin chào",
            retry_attempts=3,
        )
    )

    assert result["reason"] == reason
    assert len(calls) == 1
    assert sleeps == []


def test_send_pancake_comment_reply_retries_request_exception(monkeypatch):
    calls = []
    sleeps = []
    _set_pancake_page_tokens(monkeypatch)

    async def fake_post(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("temporary failure")
        return {
            "ok": True,
            "status_code": 200,
            "response_data": {"id": "comment-reply-1"},
        }

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(pms, "_post_pancake_reply_payload", fake_post)
    monkeypatch.setattr(pms.asyncio, "sleep", fake_sleep)

    result = asyncio.run(
        pms.send_pancake_comment_reply(
            page_id="page-1",
            conversation_id="conv-1",
            comment_message_id="comment-1",
            message="Xin chào",
            retry_attempts=2,
            retry_backoff_seconds=0.25,
        )
    )

    assert result["ok"] is True
    assert len(calls) == 2
    assert sleeps == [0.25]


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"page_id": ""}, "missing_page_id"),
        ({"conversation_id": ""}, "missing_pancake_conversation_id"),
        ({"comment_message_id": ""}, "missing_pancake_comment_message_id"),
        ({"content_ids": []}, "missing_pancake_content_ids"),
    ],
)
def test_send_pancake_comment_content_ids_validates_before_token_lookup(
    monkeypatch,
    overrides,
    reason,
):
    monkeypatch.setattr(
        pms,
        "_get_pancake_page_access_token_for_page",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not lookup token")),
    )
    kwargs = {
        "page_id": "page-1",
        "conversation_id": "conv-1",
        "comment_message_id": "comment-1",
        "content_ids": ["content-1"],
    }
    kwargs.update(overrides)

    result = asyncio.run(pms.send_pancake_comment_content_ids(**kwargs))

    assert result == {
        "ok": False,
        "reason": reason,
        "non_retryable": True,
    }


def test_send_pancake_comment_content_ids_success(monkeypatch):
    calls = []
    _set_pancake_page_tokens(monkeypatch)

    async def fake_post(*, page_access_token, page_id, conversation_id, payload, timeout):
        calls.append(
            {
                "page_access_token": page_access_token,
                "page_id": page_id,
                "conversation_id": conversation_id,
                "payload": payload,
                "timeout": timeout,
            }
        )
        return {"ok": True, "status_code": 200, "response_data": {"success": True}}

    monkeypatch.setattr(pms, "_post_pancake_reply_payload", fake_post)

    result = asyncio.run(
        pms.send_pancake_comment_content_ids(
            page_id=" page-1 ",
            conversation_id=" conv-1 ",
            comment_message_id=" comment-1 ",
            content_ids=[" content-1 ", "", "content-2"],
        )
    )

    assert result["ok"] is True
    assert calls == [
        {
            "page_access_token": "token-1",
            "page_id": "page-1",
            "conversation_id": "conv-1",
            "payload": {
                "action": "reply_comment",
                "message_id": "comment-1",
                "content_ids": ["content-1", "content-2"],
            },
            "timeout": 30.0,
        }
    ]
def test_fetch_pancake_conversation_messages_success(monkeypatch):
    calls = []
    _set_pancake_page_tokens(monkeypatch)

    async def fake_get(*, page_access_token, page_id, conversation_id, timeout):
        calls.append(
            {
                "page_access_token": page_access_token,
                "page_id": page_id,
                "conversation_id": conversation_id,
                "timeout": timeout,
            }
        )
        return {"ok": True, "status_code": 200, "response_data": {"messages": [{"id": "m-1"}]}}

    monkeypatch.setattr(pms, "_get_pancake_conversation_messages", fake_get)

    result = asyncio.run(
        pms.fetch_pancake_conversation_messages(
            page_id="page-1",
            conversation_id="conv-1",
            retry_attempts=3,
        )
    )

    assert result["ok"] is True
    assert result["response_data"] == {"messages": [{"id": "m-1"}]}
    assert calls == [
        {
            "page_access_token": "token-1",
            "page_id": "page-1",
            "conversation_id": "conv-1",
            "timeout": 30.0,
        }
    ]


def test_fetch_pancake_conversation_messages_missing_page_token_does_not_get(monkeypatch):
    _set_pancake_page_tokens(monkeypatch, {"other-page": "other-token"})

    async def fake_get(**kwargs):  # pragma: no cover - defensive
        raise AssertionError("must not call Pancake API without a page token")

    monkeypatch.setattr(pms, "_get_pancake_conversation_messages", fake_get)

    result = asyncio.run(
        pms.fetch_pancake_conversation_messages(
            page_id="page-1",
            conversation_id="conv-1",
        )
    )

    assert result == {
        "ok": False,
        "reason": pms.PANCAKE_MISSING_PAGE_ACCESS_TOKEN_FOR_PAGE_REASON,
        "non_retryable": True,
        "page_id": "page-1",
    }


def test_get_pancake_conversation_messages_uses_get_with_page_token(monkeypatch):
    calls = []

    class _FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"messages": [{"id": "m-1"}]}

    class _FakeAsyncClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, *, params):
            calls.append(
                {
                    "url": url,
                    "params": params,
                    "timeout": self.timeout,
                }
            )
            return _FakeResponse()

    monkeypatch.setattr(pms.httpx, "AsyncClient", _FakeAsyncClient)

    result = asyncio.run(
        pms._get_pancake_conversation_messages(
            page_access_token="token-1",
            page_id="page-1",
            conversation_id="conv-1",
            timeout=1.5,
        )
    )

    assert result["ok"] is True
    assert result["response_data"] == {"messages": [{"id": "m-1"}]}
    assert calls == [
        {
            "url": "https://pages.fm/api/public_api/v1/pages/page-1/conversations/conv-1/messages",
            "params": {"page_access_token": "token-1"},
            "timeout": 1.5,
        }
    ]


def test_post_pancake_reply_payload_removes_asterisks_before_http_post(monkeypatch):
    calls = []

    class _FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"success": True}

    class _FakeAsyncClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, *, params, json):
            calls.append(
                {
                    "url": url,
                    "params": params,
                    "json": json,
                }
            )
            return _FakeResponse()

    monkeypatch.setattr(pms.httpx, "AsyncClient", _FakeAsyncClient)

    result = asyncio.run(
        pms._post_pancake_reply_payload(
            page_access_token="token-1",
            page_id="page-1",
            conversation_id="conv-1",
            payload={"action": "reply_inbox", "message": "**Hello** **there**"},
            timeout=1.0,
        )
    )

    assert result["ok"] is True
    assert calls[0]["json"] == {
        "action": "reply_inbox",
        "message": "Hello there",
    }


def test_post_pancake_reply_payload_rejects_success_false_body(monkeypatch):
    class _FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"success": False, "message": "message is required"}

    class _FakeAsyncClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, *, params, json):
            return _FakeResponse()

    monkeypatch.setattr(pms.httpx, "AsyncClient", _FakeAsyncClient)

    result = asyncio.run(
        pms._post_pancake_reply_payload(
            page_access_token="token-1",
            page_id="page-1",
            conversation_id="conv-1",
            payload={
                "action": "reply_comment",
                "message_id": "comment-1",
                "content_ids": ["content-1"],
            },
            timeout=1.0,
        )
    )

    assert result["ok"] is False
    assert result["reason"] == "pancake_api_unsuccessful_response"
    assert result["non_retryable"] is True
    assert result["status_code"] == 200


def test_send_pancake_content_ids_success(monkeypatch):
    calls = []
    _set_pancake_page_tokens(monkeypatch)

    async def fake_post(*, page_access_token, page_id, conversation_id, payload, timeout):
        calls.append(
            {
                "page_access_token": page_access_token,
                "page_id": page_id,
                "conversation_id": conversation_id,
                "payload": payload,
                "timeout": timeout,
            }
        )
        return {"ok": True, "status_code": 200, "response_data": {"success": True}}

    monkeypatch.setattr(pms, "_post_pancake_reply_payload", fake_post)

    result = asyncio.run(
        pms.send_pancake_content_ids(
            page_id="page-1",
            conversation_id="conv-1",
            content_ids=["content-1", "", "content-2"],
            retry_attempts=3,
        )
    )

    assert result["ok"] is True
    assert result["response_data"] == {"success": True}
    assert len(calls) == 1
    assert calls[0]["payload"] == {
        "action": "reply_inbox",
        "content_ids": ["content-1", "content-2"],
    }
    assert calls[0]["page_access_token"] == "token-1"


def test_send_pancake_content_ids_uses_second_page_token(monkeypatch):
    calls = []
    _set_pancake_page_tokens(monkeypatch)

    async def fake_post(*, page_access_token, page_id, conversation_id, payload, timeout):
        calls.append(
            {
                "page_access_token": page_access_token,
                "page_id": page_id,
                "payload": payload,
            }
        )
        return {"ok": True, "status_code": 200, "response_data": {"success": True}}

    monkeypatch.setattr(pms, "_post_pancake_reply_payload", fake_post)

    result = asyncio.run(
        pms.send_pancake_content_ids(
            page_id="page-2",
            conversation_id="conv-2",
            content_ids=["content-2"],
        )
    )

    assert result["ok"] is True
    assert calls == [
        {
            "page_access_token": "token-2",
            "page_id": "page-2",
            "payload": {"action": "reply_inbox", "content_ids": ["content-2"]},
        }
    ]


def test_send_pancake_content_ids_missing_page_token_does_not_post(monkeypatch):
    _set_pancake_page_tokens(monkeypatch, {"other-page": "other-token"})

    async def fake_post(**kwargs):  # pragma: no cover - defensive
        raise AssertionError("must not call Pancake API without a page token")

    monkeypatch.setattr(pms, "_post_pancake_reply_payload", fake_post)

    result = asyncio.run(
        pms.send_pancake_content_ids(
            page_id="page-1",
            conversation_id="conv-1",
            content_ids=["content-1"],
        )
    )

    assert result == {
        "ok": False,
        "reason": pms.PANCAKE_MISSING_PAGE_ACCESS_TOKEN_FOR_PAGE_REASON,
        "non_retryable": True,
        "page_id": "page-1",
    }


def test_send_pancake_content_ids_requires_ids(monkeypatch):
    _set_pancake_page_tokens(monkeypatch)

    result = asyncio.run(
        pms.send_pancake_content_ids(
            page_id="page-1",
            conversation_id="conv-1",
            content_ids=[],
        )
    )

    assert result == {
        "ok": False,
        "reason": "missing_pancake_content_ids",
        "non_retryable": True,
    }


def test_extract_pancake_content_id_supports_nested_data():
    assert pms._extract_pancake_content_id({"id": "content-root"}) == "content-root"
    assert pms._extract_pancake_content_id({"data": {"content_id": "content-1"}}) == "content-1"
    assert pms._extract_pancake_content_id({"content": {"id": "content-2"}}) == "content-2"


def test_post_pancake_upload_content_posts_file_and_extracts_content_id(monkeypatch, tmp_path):
    file_path = tmp_path / "image.jpg"
    file_path.write_bytes(b"image")
    calls = []

    class _FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"content_id": "content-1"}

    class _FakeAsyncClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, *, params, files):
            calls.append(
                {
                    "url": url,
                    "params": params,
                    "file_name": files["file"][0],
                }
            )
            return _FakeResponse()

    monkeypatch.setattr(pms.httpx, "AsyncClient", _FakeAsyncClient)

    result = asyncio.run(
        pms._post_pancake_upload_content(
            page_access_token="token-1",
            page_id="page-1",
            file_path=file_path,
            timeout=1.0,
        )
    )

    assert result["ok"] is True
    assert result["content_id"] == "content-1"
    assert calls == [
        {
            "url": "https://pages.fm/api/public_api/v1/pages/page-1/upload_contents",
            "params": {"page_access_token": "token-1"},
            "file_name": "image.jpg",
        }
    ]


def test_post_pancake_upload_content_missing_content_id_returns_reason(monkeypatch, tmp_path):
    file_path = tmp_path / "image.jpg"
    file_path.write_bytes(b"image")

    class _FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"success": True}

    class _FakeAsyncClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, *, params, files):
            return _FakeResponse()

    monkeypatch.setattr(pms.httpx, "AsyncClient", _FakeAsyncClient)

    result = asyncio.run(
        pms._post_pancake_upload_content(
            page_access_token="token-1",
            page_id="page-1",
            file_path=file_path,
            timeout=1.0,
        )
    )

    assert result["ok"] is False
    assert result["reason"] == "missing_pancake_content_id"
    assert result["non_retryable"] is True


def test_upload_pancake_content_success(monkeypatch, tmp_path):
    file_path = tmp_path / "image.jpg"
    file_path.write_bytes(b"image")
    calls = []
    _set_pancake_page_tokens(monkeypatch)

    async def fake_upload(*, page_access_token, page_id, file_path, timeout):
        calls.append(
            {
                "page_access_token": page_access_token,
                "page_id": page_id,
                "file_path": file_path,
                "timeout": timeout,
            }
        )
        return {
            "ok": True,
            "status_code": 200,
            "content_id": "content-1",
            "response_data": {"content_id": "content-1"},
        }

    monkeypatch.setattr(pms, "_post_pancake_upload_content", fake_upload)

    result = asyncio.run(
        pms.upload_pancake_content(
            page_id="page-1",
            file_path=str(file_path),
            retry_attempts=2,
        )
    )

    assert result["ok"] is True
    assert result["content_id"] == "content-1"
    assert len(calls) == 1
    assert calls[0]["page_access_token"] == "token-1"
    assert calls[0]["page_id"] == "page-1"
    assert calls[0]["file_path"] == file_path


def test_upload_pancake_content_requires_existing_file(monkeypatch):
    _set_pancake_page_tokens(monkeypatch)

    result = asyncio.run(
        pms.upload_pancake_content(
            page_id="page-1",
            file_path="missing.jpg",
        )
    )

    assert result == {
        "ok": False,
        "reason": "pancake_upload_file_not_found",
        "non_retryable": True,
    }


def test_upload_pancake_content_missing_page_token_does_not_upload(monkeypatch, tmp_path):
    file_path = tmp_path / "image.jpg"
    file_path.write_bytes(b"image")
    _set_pancake_page_tokens(monkeypatch, {"other-page": "other-token"})

    async def fake_upload(**kwargs):  # pragma: no cover - defensive
        raise AssertionError("must not upload without a page token")

    monkeypatch.setattr(pms, "_post_pancake_upload_content", fake_upload)

    result = asyncio.run(
        pms.upload_pancake_content(
            page_id="page-1",
            file_path=str(file_path),
        )
    )

    assert result == {
        "ok": False,
        "reason": pms.PANCAKE_MISSING_PAGE_ACCESS_TOKEN_FOR_PAGE_REASON,
        "non_retryable": True,
        "page_id": "page-1",
    }


def test_send_pancake_reply_does_not_retry_non_retryable_error(monkeypatch):
    calls = []
    sleeps = []
    _set_pancake_page_tokens(monkeypatch)

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    async def fake_post(*, page_access_token, page_id, conversation_id, payload, timeout):
        calls.append(payload)
        return {
            "ok": False,
            "reason": "pancake_auth_error",
            "non_retryable": True,
            "status_code": 401,
        }

    monkeypatch.setattr(pms, "_post_pancake_reply_payload", fake_post)
    monkeypatch.setattr(pms.asyncio, "sleep", fake_sleep)

    result = asyncio.run(
        pms.send_pancake_reply(
            page_id="page-1",
            conversation_id="conv-1",
            message="Xin chào",
            retry_attempts=3,
        )
    )

    assert result["ok"] is False
    assert result["reason"] == "pancake_auth_error"
    assert len(calls) == 1
    assert sleeps == []


def test_send_pancake_reply_retries_temporary_error(monkeypatch):
    calls = []
    sleeps = []
    _set_pancake_page_tokens(monkeypatch)

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    async def fake_post(*, page_access_token, page_id, conversation_id, payload, timeout):
        calls.append(payload)
        if len(calls) == 1:
            return {
                "ok": False,
                "reason": "pancake_api_error",
                "non_retryable": False,
                "status_code": 500,
            }
        return {"ok": True, "status_code": 200, "response_data": {"id": "reply-2"}}

    monkeypatch.setattr(pms, "_post_pancake_reply_payload", fake_post)
    monkeypatch.setattr(pms.asyncio, "sleep", fake_sleep)

    result = asyncio.run(
        pms.send_pancake_reply(
            page_id="page-1",
            conversation_id="conv-1",
            message="Xin chào",
            retry_attempts=2,
            retry_backoff_seconds=0.5,
        )
    )

    assert result["ok"] is True
    assert result["response_data"] == {"id": "reply-2"}
    assert len(calls) == 2
    assert sleeps == [0.5]


def test_classify_pancake_error_marks_auth_as_non_retryable():
    result = pms._classify_pancake_error(status_code=403, error_body={"error": "bad token"})

    assert result["reason"] == "pancake_auth_error"
    assert result["non_retryable"] is True
    assert result["status_code"] == 403
