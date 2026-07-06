import asyncio

from app.services import facebook_message_service as fms


def _image_url(index: int) -> str:
    return f"https://lh3.googleusercontent.com/d/image_{index}"


def test_split_text_and_image_urls_removes_allowed_images_from_text():
    result = fms.split_text_and_image_urls(
        "Dạ gửi bạn ảnh sản phẩm:\n"
        "https://lh3.googleusercontent.com/d/image_1\n"
        "Ảnh nữa https://lh3.googleusercontent.com/d/image_2."
    )

    assert result.text == "Dạ gửi bạn ảnh sản phẩm:\nẢnh nữa"
    assert result.image_urls == [
        "https://lh3.googleusercontent.com/d/image_1",
        "https://lh3.googleusercontent.com/d/image_2",
    ]


def test_split_text_and_image_urls_deduplicates_and_limits_to_30():
    message = "\n".join([_image_url(1), _image_url(1), *[_image_url(index) for index in range(2, 33)]])

    result = fms.split_text_and_image_urls(message)

    assert result.text == ""
    assert len(result.image_urls) == 30
    assert result.image_urls[0] == _image_url(1)
    assert result.image_urls[-1] == _image_url(30)
    assert result.skipped_count == 1
    assert result.truncated_count == 2


def test_split_text_and_image_urls_keeps_non_image_urls_in_text():
    result = fms.split_text_and_image_urls(
        "Xem thêm https://example.com/not-image và ảnh https://lh3.googleusercontent.com/d/image_1"
    )

    assert result.text == "Xem thêm https://example.com/not-image và ảnh"
    assert result.image_urls == ["https://lh3.googleusercontent.com/d/image_1"]
    assert result.skipped_count == 1


def test_build_facebook_text_payload_sets_metadata():
    payload = fms.build_facebook_text_payload(
        recipient_id="fb_user_1",
        message_text="Xin chào",
        reply_to_mid="m_001",
    )

    assert payload == {
        "messaging_type": "RESPONSE",
        "recipient": {"id": "fb_user_1"},
        "message": {
            "text": "Xin chào",
            "metadata": "source_mid:m_001",
        },
    }


def test_build_facebook_attachments_payload_uses_bulk_schema():
    payload = fms.build_facebook_image_attachments_payload(
        recipient_id="fb_user_1",
        image_urls=[_image_url(1), _image_url(2)],
    )

    assert payload == {
        "messaging_type": "RESPONSE",
        "recipient": {"id": "fb_user_1"},
        "message": {
            "attachments": [
                {"type": "image", "payload": {"url": _image_url(1)}},
                {"type": "image", "payload": {"url": _image_url(2)}},
            ]
        },
    }


def test_build_facebook_send_api_url_uses_v21_page_id_endpoint():
    assert fms.build_facebook_send_api_url(page_id="970198996185881") == (
        "https://graph.facebook.com/v21.0/970198996185881/messages"
    )


def test_build_facebook_send_api_url_falls_back_to_me_endpoint_without_page_id():
    assert fms.build_facebook_send_api_url() == "https://graph.facebook.com/v21.0/me/messages"


def test_send_facebook_images_bulk_success_does_not_fallback(monkeypatch):
    calls = []

    async def fake_post(*, page_access_token, payload, page_id=None, timeout=30.0):
        calls.append({"payload": payload, "page_id": page_id})
        return {"ok": True, "data": {"message_id": "bulk"}}

    monkeypatch.setattr(fms, "_post_facebook_message_payload", fake_post)

    result = asyncio.run(
        fms.send_facebook_images(
            recipient_id="fb_user_1",
            image_urls=[_image_url(1), _image_url(2)],
            page_access_token="page-token",
            page_id="970198996185881",
        )
    )

    assert result["ok"] is True
    assert result["sent_count"] == 2
    assert result["bulk_succeeded"] is True
    assert len(calls) == 1
    assert calls[0]["page_id"] == "970198996185881"
    assert "attachments" in calls[0]["payload"]["message"]


def test_send_facebook_images_fallbacks_to_single_payloads(monkeypatch):
    calls = []
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    async def fake_post(*, page_access_token, payload, page_id=None, timeout=30.0):
        calls.append(payload)
        if len(calls) <= 2:
            return {"ok": False, "status_code": 400, "error": "bulk unsupported"}
        if len(calls) == 4:
            return {"ok": False, "status_code": 403, "error": "bad image"}
        return {"ok": True, "data": {"message_id": f"single-{len(calls)}"}}

    monkeypatch.setattr(fms, "_post_facebook_message_payload", fake_post)
    monkeypatch.setattr(fms.asyncio, "sleep", fake_sleep)

    result = asyncio.run(
        fms.send_facebook_images(
            recipient_id="fb_user_1",
            image_urls=[_image_url(1), _image_url(2), _image_url(3)],
            page_access_token="page-token",
        )
    )

    assert result["ok"] is True
    assert result["bulk_attempted"] is True
    assert result["bulk_succeeded"] is False
    assert result["bulk_attempt_count"] == 2
    assert result["sent_count"] == 2
    assert result["failed_count"] == 1
    assert sleeps == [fms.FACEBOOK_BULK_RETRY_DELAY_SECONDS]
    assert len(calls) == 5
    assert "attachments" in calls[0]["message"]
    assert "attachments" in calls[1]["message"]
    assert all("attachment" in payload["message"] for payload in calls[2:])


def test_send_facebook_images_retries_bulk_once_before_fallback(monkeypatch):
    calls = []
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    async def fake_post(*, page_access_token, payload, page_id=None, timeout=30.0):
        calls.append(payload)
        if len(calls) == 1:
            return {"ok": False, "status_code": 400, "error": "temporary attachment fetch failure"}
        return {"ok": True, "data": {"message_id": "bulk-retry"}}

    monkeypatch.setattr(fms, "_post_facebook_message_payload", fake_post)
    monkeypatch.setattr(fms.asyncio, "sleep", fake_sleep)

    result = asyncio.run(
        fms.send_facebook_images(
            recipient_id="fb_user_1",
            image_urls=[_image_url(1), _image_url(2), _image_url(3)],
            page_access_token="page-token",
        )
    )

    assert result["ok"] is True
    assert result["bulk_succeeded"] is True
    assert result["bulk_attempt_count"] == 2
    assert result["sent_count"] == 3
    assert sleeps == [fms.FACEBOOK_BULK_RETRY_DELAY_SECONDS]
    assert len(calls) == 2
    assert all("attachments" in payload["message"] for payload in calls)


def test_send_facebook_images_non_retryable_bulk_failure_does_not_retry(monkeypatch):
    calls = []
    sleeps = []

    async def fake_sleep(seconds):  # pragma: no cover - defensive
        sleeps.append(seconds)

    async def fake_post(*, page_access_token, payload, page_id=None, timeout=30.0):
        calls.append(payload)
        return {
            "ok": False,
            "reason": "facebook_auth_error",
            "non_retryable": True,
            "status_code": 400,
            "error": "bad token",
        }

    monkeypatch.setattr(fms, "_post_facebook_message_payload", fake_post)
    monkeypatch.setattr(fms.asyncio, "sleep", fake_sleep)

    result = asyncio.run(
        fms.send_facebook_images(
            recipient_id="fb_user_1",
            image_urls=[_image_url(1), _image_url(2), _image_url(3)],
            page_access_token="bad-token",
        )
    )

    assert result["ok"] is False
    assert result["reason"] == "facebook_auth_error"
    assert result["non_retryable"] is True
    assert result["failed_count"] == 3
    assert result["bulk_attempt_count"] == 1
    assert sleeps == []
    assert len(calls) == 1


def test_send_facebook_images_all_single_fallbacks_fail_without_crashing(monkeypatch):
    calls = []
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    async def fake_post(*, page_access_token, payload, page_id=None, timeout=30.0):
        calls.append(payload)
        return {"ok": False, "status_code": 403, "error": "bad image"}

    monkeypatch.setattr(fms, "_post_facebook_message_payload", fake_post)
    monkeypatch.setattr(fms.asyncio, "sleep", fake_sleep)

    result = asyncio.run(
        fms.send_facebook_images(
            recipient_id="fb_user_1",
            image_urls=[_image_url(1), _image_url(2)],
            page_access_token="page-token",
        )
    )

    assert result["ok"] is False
    assert result["bulk_attempted"] is True
    assert result["bulk_succeeded"] is False
    assert result["sent_count"] == 0
    assert result["failed_count"] == 2
    assert result["bulk_attempt_count"] == 2
    assert sleeps == [fms.FACEBOOK_BULK_RETRY_DELAY_SECONDS]
    assert len(calls) == 4


def test_send_facebook_images_caps_bulk_payload_at_30(monkeypatch):
    calls = []

    async def fake_post(*, page_access_token, payload, page_id=None, timeout=30.0):
        calls.append(payload)
        return {"ok": True}

    monkeypatch.setattr(fms, "_post_facebook_message_payload", fake_post)

    result = asyncio.run(
        fms.send_facebook_images(
            recipient_id="fb_user_1",
            image_urls=[_image_url(index) for index in range(31)],
            page_access_token="page-token",
        )
    )

    assert result["sent_count"] == 30
    assert result["truncated_count"] == 1
    assert len(calls[0]["message"]["attachments"]) == 30


def test_send_facebook_text_and_images_sends_text_before_images(monkeypatch):
    calls = []

    async def fake_post(*, page_access_token, payload, page_id=None, timeout=30.0):
        calls.append({"payload": payload, "page_id": page_id})
        return {"ok": True, "data": {"message_id": str(len(calls))}}

    monkeypatch.setattr(fms, "_post_facebook_message_payload", fake_post)

    result = asyncio.run(
        fms.send_facebook_text_and_images(
            recipient_id="fb_user_1",
            message_text=f"Đây là mẫu phù hợp {_image_url(1)}",
            page_access_token="page-token",
            page_id="970198996185881",
            reply_to_mid="m_001",
        )
    )

    assert result["ok"] is True
    assert result["text"] == "Đây là mẫu phù hợp"
    assert calls[0]["page_id"] == "970198996185881"
    assert calls[1]["page_id"] == "970198996185881"
    assert calls[0]["payload"]["message"]["text"] == "Đây là mẫu phù hợp"
    assert calls[0]["payload"]["message"]["metadata"] == "source_mid:m_001"
    assert "attachment" in calls[1]["payload"]["message"]


def test_send_facebook_text_and_images_accepts_prepared_image_urls_and_caps_at_three(monkeypatch):
    calls = []

    async def fake_post(*, page_access_token, payload, page_id=None, timeout=30.0):
        calls.append(payload)
        return {"ok": True, "data": {"message_id": str(len(calls))}}

    monkeypatch.setattr(fms, "_post_facebook_message_payload", fake_post)

    result = asyncio.run(
        fms.send_facebook_text_and_images(
            recipient_id="fb_user_1",
            message_text="Dạ em gửi ảnh mẫu này cho chị ạ.",
            image_urls=[_image_url(index) for index in range(1, 5)],
            page_access_token="page-token",
            reply_to_mid="m_001",
        )
    )

    assert result["ok"] is True
    assert result["image_urls"] == [_image_url(1), _image_url(2), _image_url(3)]
    assert result["truncated_image_url_count"] == 1
    assert calls[0]["message"]["text"] == "Dạ em gửi ảnh mẫu này cho chị ạ."
    assert [item["payload"]["url"] for item in calls[1]["message"]["attachments"]] == [
        _image_url(1),
        _image_url(2),
        _image_url(3),
    ]
