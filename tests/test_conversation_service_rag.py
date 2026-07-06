import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services import conversation_service as cs


def test_decide_next_action_service_returns_ask_slot_when_missing_slots_exist():
    action, slot, reason = cs.decide_next_action_service(
        missing_slots=["wedding_date"],
        slots={"service_interest": "cả hai"},
    )

    assert action == "ask_slot"
    assert slot == "wedding_date"
    assert reason == "missing_slot_detected"


def test_decide_next_action_service_returns_call_rag_when_no_missing_slots():
    action, slot, reason = cs.decide_next_action_service(
        missing_slots=[],
        slots={"wedding_date": "28/03/2026"},
    )

    assert action == "call_rag"
    assert slot is None
    assert reason == "no_missing_slot_call_rag"


def test_build_rag_payload_uses_structured_question_without_branch_context(monkeypatch):
    history = [
        {"role": "user", "content": "Bên mình có gói prewedding nào phù hợp không?"},
        {"role": "assistant", "content": "Dạ anh/chị đang quan tâm studio hay ngoại cảnh ạ?"},
    ]

    async def fake_history(conversation_id, limit=5):
        assert conversation_id == "conv-123"
        assert limit == 5
        return history

    monkeypatch.setattr(cs, "_get_recent_conversation_history", fake_history)

    latest_user_message = "Mình muốn album nhựa khoảng 500 tấm và có khung."
    branch = "prewedding_consultation"
    slots = {
        "wedding_date": "28/03/2026",
        "desired_products_details": "album nhựa, 500 tấm, có khung",
    }

    payload = asyncio.run(
        cs._build_rag_payload(
            latest_user_message=latest_user_message,
            branch=branch,
            slots=slots,
            conversation_id="conv-123",
        )
    )

    question = payload.get("question", "")
    wedding_date_def = cs.get_slot_definition("wedding_date") or {}
    desired_products_def = cs.get_slot_definition("desired_products_details") or {}

    assert "question" in payload
    assert "conversation_history" in payload
    assert payload["conversation_history"] == history

    assert "Nhu cầu khách:" in question
    assert history[0]["content"] in question
    assert "Thông tin đã xác nhận:" in question
    assert "Ngữ cảnh tư vấn hiện tại:" not in question
    assert history[1]["content"] not in question
    assert (wedding_date_def.get("label") or "") in question
    assert (desired_products_def.get("label") or "") in question
    assert "wedding_date" not in question
    assert "desired_products_details" not in question


def test_extract_rag_anchor_keeps_stored_anchor_for_slot_answer_turn():
    history = [
        {"role": "user", "content": "Cho em hỏi dịch vụ chụp ảnh ngày cưới ạ"},
        {"role": "assistant", "content": "Dạ anh/chị đã có ngày cưới cụ thể chưa ạ?"},
        {"role": "user", "content": "Dạ em cưới ngày 28/03/2026 ạ"},
    ]

    anchor = cs.extract_rag_anchor(
        current_user_message="Dạ em cưới ngày 28/03/2026 ạ",
        current_intent="ask_service_info",
        previous_next_slot="wedding_date",
        current_slots={"wedding_date": "28/03/2026"},
        recent_conversation_history=history,
        stored_rag_anchor="Cho em hỏi dịch vụ chụp ảnh ngày cưới ạ",
    )

    assert anchor == "Cho em hỏi dịch vụ chụp ảnh ngày cưới ạ"


def test_build_rag_payload_keeps_old_anchor_when_latest_turn_is_slot_answer():
    history = [
        {"role": "user", "content": "Cho em hỏi dịch vụ chụp ảnh ngày cưới ạ"},
        {"role": "assistant", "content": "Dạ anh/chị đã có ngày cưới cụ thể chưa ạ?"},
        {"role": "user", "content": "Dạ em cưới ngày 28/03/2026 ạ"},
    ]

    payload = asyncio.run(
        cs._build_rag_payload(
            latest_user_message="Dạ em cưới ngày 28/03/2026 ạ",
            branch="greeting_initial_qualification",
            slots={"wedding_date": "28/03/2026"},
            conversation_id="conv-123",
            current_intent="ask_service_info",
            previous_next_slot="wedding_date",
            current_slots={"wedding_date": "28/03/2026"},
            stored_rag_anchor="Cho em hỏi dịch vụ chụp ảnh ngày cưới ạ",
            recent_conversation_history=history,
        )
    )

    question = payload.get("question", "")
    assert "Nhu cầu khách: Cho em hỏi dịch vụ chụp ảnh ngày cưới ạ" in question
    assert "Dạ em cưới ngày 28/03/2026 ạ" not in question
    assert "Ngữ cảnh tư vấn hiện tại:" not in question


def test_extract_rag_anchor_backfills_from_history_when_no_stored_anchor():
    history = [
        {"role": "user", "content": "Cho em hỏi dịch vụ chụp ảnh ngày cưới ạ"},
        {"role": "assistant", "content": "Dạ anh/chị đã có ngày cưới cụ thể chưa ạ?"},
        {"role": "user", "content": "Dạ em cưới ngày 28/03/2026 ạ"},
    ]

    anchor = cs.extract_rag_anchor(
        current_user_message="Dạ em cưới ngày 28/03/2026 ạ",
        current_intent="ask_service_info",
        previous_next_slot="wedding_date",
        current_slots={"wedding_date": "28/03/2026"},
        recent_conversation_history=history,
        stored_rag_anchor=None,
    )

    assert anchor == "Cho em hỏi dịch vụ chụp ảnh ngày cưới ạ"


def test_render_slot_summary_normalizes_and_sorts(monkeypatch):
    slot_defs = {
        "wedding_date": {"label": "Ngày cưới", "slot_type": "date", "priority": "high"},
        "wedding_day_services_needed": {
            "label": "Dịch vụ ngày cưới cần dùng",
            "slot_type": "multi_select",
            "priority": "high",
        },
        "event_idea_status": {"label": "Đã có ý tưởng", "slot_type": "boolean", "priority": "medium"},
        "desired_products_details": {
            "label": "Mong muốn về sản phẩm/chi tiết gói",
            "slot_type": "dict",
            "priority": "low",
        },
    }
    monkeypatch.setattr(cs, "get_slot_definition", lambda slot_name: slot_defs.get(slot_name))

    summary = cs.render_slot_summary(
        slots={
            "event_idea_status": "true",
            "wedding_date": "28/03/2026",
            "wedding_day_services_needed": ["chụp", "quay"],
            "desired_products_details": {"photo_count": 500, "material": "album nhựa"},
            "noise_slot": "   ",
        }
    )

    assert summary == [
        "Dịch vụ ngày cưới cần dùng: chụp, quay",
        "Ngày cưới: 28/03/2026",
        "Đã có ý tưởng: đã có",
        "Mong muốn về sản phẩm/chi tiết gói: material: album nhựa, photo_count: 500",
    ]


def test_is_rag_no_data_answer_accepts_informative_answer_with_partial_disclaimer():
    answer = (
        "Dưới đây là các gói pre-wedding phù hợp.\n"
        "Lưu ý: hiện không có thông tin xác nhận riêng cho bãi dài cam ranh trong tài liệu."
    )
    assert cs._is_rag_no_data_answer(answer) is False


def test_is_rag_no_data_answer_accepts_informative_answer_with_no_data_phrase():
    answer = (
        "Không tìm thấy thông tin xác nhận riêng cho địa điểm trong tài liệu.\n"
        "Dưới đây là các gói phù hợp:\n"
        "- NGOẠI CẢNH BASIC | Giá: 9.500.000đ | Bao gồm album, makeup."
    )
    assert cs._is_rag_no_data_answer(answer) is False


def test_is_rag_no_data_answer_detects_explicit_no_data_response():
    answer = "Không tìm thấy thông tin phù hợp trong tài liệu."
    assert cs._is_rag_no_data_answer(answer) is True


def test_get_valid_rag_access_token_uses_cached_token_when_not_stale(monkeypatch):
    now = cs.now_vn()
    cached_row = SimpleNamespace(
        access_token="cached-token",
        updated_at=now - timedelta(days=2),
        created_at=now - timedelta(days=8),
    )

    monkeypatch.setattr(cs, "_get_rag_token_refresh_days", lambda: 6)
    monkeypatch.setattr(cs, "now_vn", lambda: now)
    monkeypatch.setattr(cs, "_get_latest_rag_token_row", AsyncMock(return_value=cached_row))

    login_mock = AsyncMock(return_value=("new-token", "bearer"))
    upsert_mock = AsyncMock()
    monkeypatch.setattr(cs, "_login_rag_and_get_token", login_mock)
    monkeypatch.setattr(cs, "_upsert_rag_token_row", upsert_mock)

    token, debug = asyncio.run(cs._get_valid_rag_access_token(force_refresh=False))

    assert token == "cached-token"
    assert debug["source"] == "db_cache"
    login_mock.assert_not_awaited()
    upsert_mock.assert_not_awaited()


def test_get_valid_rag_access_token_uses_cached_token_with_naive_updated_at(monkeypatch):
    now = cs.now_vn()
    naive_updated_at = (now - timedelta(days=2)).replace(tzinfo=None)
    cached_row = SimpleNamespace(
        access_token="cached-token-naive",
        updated_at=naive_updated_at,
        created_at=naive_updated_at,
    )

    monkeypatch.setattr(cs, "_get_rag_token_refresh_days", lambda: 6)
    monkeypatch.setattr(cs, "now_vn", lambda: now)
    monkeypatch.setattr(cs, "_get_latest_rag_token_row", AsyncMock(return_value=cached_row))

    login_mock = AsyncMock(return_value=("new-token", "bearer"))
    upsert_mock = AsyncMock()
    monkeypatch.setattr(cs, "_login_rag_and_get_token", login_mock)
    monkeypatch.setattr(cs, "_upsert_rag_token_row", upsert_mock)

    token, debug = asyncio.run(cs._get_valid_rag_access_token(force_refresh=False))

    assert token == "cached-token-naive"
    assert debug["source"] == "db_cache"
    login_mock.assert_not_awaited()
    upsert_mock.assert_not_awaited()


def test_get_valid_rag_access_token_creates_token_when_no_existing_record(monkeypatch):
    now = cs.now_vn()
    created_row = SimpleNamespace(
        access_token="created-token",
        updated_at=now,
        created_at=now,
    )

    monkeypatch.setattr(cs, "_get_rag_token_refresh_days", lambda: 6)
    monkeypatch.setattr(cs, "now_vn", lambda: now)
    monkeypatch.setattr(cs, "_get_latest_rag_token_row", AsyncMock(return_value=None))

    login_mock = AsyncMock(return_value=("created-token", "bearer"))
    upsert_mock = AsyncMock(return_value=created_row)
    monkeypatch.setattr(cs, "_login_rag_and_get_token", login_mock)
    monkeypatch.setattr(cs, "_upsert_rag_token_row", upsert_mock)

    token, debug = asyncio.run(cs._get_valid_rag_access_token(force_refresh=False))

    assert token == "created-token"
    assert debug["source"] == "login_refresh"
    login_mock.assert_awaited_once()
    upsert_mock.assert_awaited_once_with(access_token="created-token", token_type="bearer")


def test_get_valid_rag_access_token_refreshes_when_token_age_is_six_days(monkeypatch):
    now = cs.now_vn()
    stale_row = SimpleNamespace(
        access_token="old-token",
        updated_at=now - timedelta(days=6),
        created_at=now - timedelta(days=10),
    )
    refreshed_row = SimpleNamespace(
        access_token="fresh-token",
        updated_at=now,
        created_at=now - timedelta(days=10),
    )

    monkeypatch.setattr(cs, "_get_rag_token_refresh_days", lambda: 6)
    monkeypatch.setattr(cs, "now_vn", lambda: now)
    monkeypatch.setattr(cs, "_get_latest_rag_token_row", AsyncMock(return_value=stale_row))

    login_mock = AsyncMock(return_value=("fresh-token", "bearer"))
    upsert_mock = AsyncMock(return_value=refreshed_row)
    monkeypatch.setattr(cs, "_login_rag_and_get_token", login_mock)
    monkeypatch.setattr(cs, "_upsert_rag_token_row", upsert_mock)

    token, debug = asyncio.run(cs._get_valid_rag_access_token(force_refresh=False))

    assert token == "fresh-token"
    assert debug["source"] == "login_refresh"
    login_mock.assert_awaited_once()
    upsert_mock.assert_awaited_once_with(access_token="fresh-token", token_type="bearer")


class _FakeResponse:
    def __init__(self, *, status_code: int, data):
        self.status_code = status_code
        self._data = data
        self.text = str(data)

    def json(self):
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


def test_call_rag_service_injects_authorization_header(monkeypatch):
    monkeypatch.setenv("RAG_SERVICE_URL", "https://rag.example.com/qna")
    monkeypatch.setenv("RAG_SERVICE_METHOD", "POST")
    monkeypatch.setenv("RAG_SERVICE_HEADERS", "{\"X-Test\":\"1\"}")

    monkeypatch.setattr(
        cs,
        "_get_valid_rag_access_token",
        AsyncMock(return_value=("token-123", {"source": "db_cache"})),
    )

    captured_headers = {}

    async def fake_send_rag_request(*, client, rag_method, rag_url, rag_headers, payload):
        del client
        assert rag_method == "POST"
        assert rag_url == "https://rag.example.com/qna"
        captured_headers.update(rag_headers)
        return _FakeResponse(status_code=200, data={"answer": "Dạ có gói phù hợp ạ"})

    monkeypatch.setattr(cs, "_send_rag_request", fake_send_rag_request)

    answer, debug = asyncio.run(
        cs.call_rag_service(
            latest_user_message="Cho em hỏi gói chụp prewedding",
            branch="prewedding",
            intent="ask_service_info",
            slots={"wedding_date": "10/10/2026"},
            conversation_id="conv-1",
            prebuilt_payload={"question": "mock", "conversation_history": []},
            customer_name="A",
            customer_id="1",
            channel="facebook",
        )
    )

    assert answer == "Dạ có gói phù hợp ạ"
    assert debug["reason"] == "rag_answer_generated"
    assert captured_headers["Authorization"] == "Bearer token-123"
    assert captured_headers["X-Test"] == "1"


def test_call_rag_service_retries_once_when_first_response_is_401(monkeypatch):
    monkeypatch.setenv("RAG_SERVICE_URL", "https://rag.example.com/qna")
    monkeypatch.setenv("RAG_SERVICE_METHOD", "POST")

    token_mock = AsyncMock(
        side_effect=[
            ("old-token", {"source": "db_cache"}),
            ("new-token", {"source": "login_refresh"}),
        ]
    )
    monkeypatch.setattr(cs, "_get_valid_rag_access_token", token_mock)

    call_headers = []

    async def fake_send_rag_request(*, client, rag_method, rag_url, rag_headers, payload):
        del client, rag_method, rag_url, payload
        call_headers.append(dict(rag_headers))
        if len(call_headers) == 1:
            return _FakeResponse(status_code=401, data={"detail": "Unauthorized"})
        return _FakeResponse(status_code=200, data={"answer": "Token mới đã hoạt động"})

    monkeypatch.setattr(cs, "_send_rag_request", fake_send_rag_request)

    answer, debug = asyncio.run(
        cs.call_rag_service(
            latest_user_message="Cho em hỏi gói cưới",
            branch="wedding",
            intent="ask_service_info",
            slots={},
            conversation_id="conv-2",
            prebuilt_payload={"question": "mock", "conversation_history": []},
            customer_name="A",
            customer_id="1",
            channel="facebook",
        )
    )

    assert answer == "Token mới đã hoạt động"
    assert debug["reason"] == "rag_answer_generated"
    assert debug["retried_401"] is True
    assert call_headers[0]["Authorization"] == "Bearer old-token"
    assert call_headers[1]["Authorization"] == "Bearer new-token"
    assert token_mock.await_args_list[0].kwargs["force_refresh"] is False
    assert token_mock.await_args_list[1].kwargs["force_refresh"] is True


def test_call_rag_service_returns_auth_failed_when_token_resolution_fails(monkeypatch):
    monkeypatch.setenv("RAG_SERVICE_URL", "https://rag.example.com/qna")
    monkeypatch.setattr(
        cs,
        "_get_valid_rag_access_token",
        AsyncMock(side_effect=ValueError("missing_rag_auth_credentials")),
    )

    answer, debug = asyncio.run(
        cs.call_rag_service(
            latest_user_message="Xin tư vấn giúp em",
            branch="prewedding",
            intent="ask_service_info",
            slots={},
            conversation_id="conv-3",
            prebuilt_payload={"question": "mock", "conversation_history": []},
            customer_name="A",
            customer_id="1",
            channel="facebook",
        )
    )

    assert answer is None
    assert debug["reason"] == "rag_auth_failed"
    assert debug["error_type"] == "ValueError"
