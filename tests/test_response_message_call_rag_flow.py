import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1 import response_message as rm


class _DeleteQuery:
    async def delete(self):
        return None


class _FieldExpr:
    def __eq__(self, other):
        return ("eq", other)


class _FakeConversation:
    def __init__(self):
        self.id = "conv-1"
        self.customer_name = "Nguyen Van A"
        self.customer_id = "fb_123"
        self.channel = "facebook"
        self.updated_at = None

    async def save(self):
        return None


class _FakeState:
    def __init__(self):
        self.id = "state-1"
        self.branch_id = "branch-1"
        self.message_id = "msg-user-1"
        self.intent = None
        self.rag_anchor_text = "Cho em hỏi dịch vụ chụp ảnh ngày cưới ạ"
        self.next_action = None
        self.prev_slot = None
        self.next_slot = None
        self.updated_at = None

    async def save(self):
        return None


def _setup_call_rag_flow(monkeypatch, *, rag_answer, rag_debug):
    conversation = _FakeConversation()
    state = _FakeState()
    user_text = "Mình muốn tư vấn gói prewedding phù hợp."

    branch_doc = SimpleNamespace(name="prewedding_consultation")
    user_message = SimpleNamespace(
        id="msg-user-1",
        role="user",
        content=user_text,
    )

    monkeypatch.setattr(rm, "get_conversation_by_id_service", AsyncMock(return_value=conversation))
    monkeypatch.setattr(rm, "get_latest_conversation_by_customer_name_service", AsyncMock(return_value=None))
    monkeypatch.setattr(rm, "create_conversation_service", AsyncMock(return_value=conversation))
    monkeypatch.setattr(rm, "update_conversation_profile_service", AsyncMock(return_value=conversation))

    monkeypatch.setattr(rm.Branch, "get", AsyncMock(return_value=branch_doc))
    monkeypatch.setattr(rm.cs, "_get_previous_state", AsyncMock(return_value=state))
    monkeypatch.setattr(rm.cs, "_get_state_slots_map", AsyncMock(return_value={"wedding_date": "28/03/2026"}))
    monkeypatch.setattr(rm.cs, "_get_state_asked_slots", AsyncMock(return_value=[]))
    monkeypatch.setattr(rm.cs, "_get_state_missing_slots", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        rm.cs,
        "_get_recent_conversation_history",
        AsyncMock(return_value=[{"role": "user", "content": user_text}]),
    )
    monkeypatch.setattr(rm.cs, "_build_conversation_detail", AsyncMock(return_value={"id": "conv-1"}))

    notify_admins_mock = AsyncMock(return_value={"sent": 1})
    monkeypatch.setattr(rm.cs, "_notify_handoff_admins", notify_admins_mock)

    captured_payload_args = {}

    async def fake_build_rag_payload(
        *,
        latest_user_message,
        branch,
        slots,
        conversation_id,
        current_intent,
        previous_next_slot,
        current_slots,
        stored_rag_anchor,
        recent_conversation_history,
    ):
        captured_payload_args.update(
            {
                "latest_user_message": latest_user_message,
                "branch": branch,
                "slots": slots,
                "conversation_id": conversation_id,
                "current_intent": current_intent,
                "previous_next_slot": previous_next_slot,
                "current_slots": current_slots,
                "stored_rag_anchor": stored_rag_anchor,
                "recent_conversation_history": recent_conversation_history,
            }
        )
        return {
            "question": "mocked question",
            "conversation_history": [{"role": "user", "content": "hello"}],
        }

    monkeypatch.setattr(rm.cs, "_build_rag_payload", fake_build_rag_payload)
    monkeypatch.setattr(rm.cs, "call_rag_service", AsyncMock(return_value=(rag_answer, rag_debug)))

    monkeypatch.setattr(rm.Message, "get", AsyncMock(return_value=user_message))
    monkeypatch.setattr(
        rm.Message,
        "find_one",
        AsyncMock(return_value=SimpleNamespace(id="bot-message-existing")),
    )
    monkeypatch.setattr(
        rm.StateAskedSlot,
        "conversation_state_id",
        _FieldExpr(),
        raising=False,
    )
    monkeypatch.setattr(rm.StateAskedSlot, "find", lambda *args, **kwargs: _DeleteQuery())

    result = asyncio.run(
        rm.run_response_message_flow(
            text=user_text,
            conversation_id="conv-1",
            channel="facebook",
            customer_name="Nguyen Van A",
            extracted_branch_name="prewedding_consultation",
            extracted_intent="ask_service_info",
            extracted_branch="prewedding_consultation",
            extracted_slots={},
        )
    )
    return result, captured_payload_args, notify_admins_mock


def test_run_response_message_flow_returns_rag_answer_when_available(monkeypatch):
    rag_debug = {"reason": "rag_answer_generated"}
    result, captured_payload_args, notify_admins_mock = _setup_call_rag_flow(
        monkeypatch,
        rag_answer="Dạ bên em có gói phù hợp ạ.",
        rag_debug=rag_debug,
    )

    assert result["state"]["next_action"] == "call_rag"
    assert result["assistant_message"] == "Dạ bên em có gói phù hợp ạ."
    assert result["debug"]["next_action_reason"] == "no_missing_slot_call_rag"
    assert captured_payload_args["latest_user_message"] == "Mình muốn tư vấn gói prewedding phù hợp."
    assert captured_payload_args["branch"] == "prewedding_consultation"
    assert captured_payload_args["conversation_id"] == "conv-1"
    assert captured_payload_args["stored_rag_anchor"] == "Cho em hỏi dịch vụ chụp ảnh ngày cưới ạ"
    assert captured_payload_args["recent_conversation_history"] == [{"role": "user", "content": "Mình muốn tư vấn gói prewedding phù hợp."}]
    notify_admins_mock.assert_not_awaited()


@pytest.mark.parametrize(
    "rag_debug",
    [
        {"reason": "rag_no_data_found"},
        {"reason": "rag_http_error", "status_code": 500},
    ],
)
def test_run_response_message_flow_fallbacks_to_handoff_on_rag_failure(monkeypatch, rag_debug):
    result, _, notify_admins_mock = _setup_call_rag_flow(
        monkeypatch,
        rag_answer=None,
        rag_debug=rag_debug,
    )

    assert result["state"]["next_action"] == "handoff"
    assert result["state"]["next_slot"] is None
    assert result["assistant_message"] == rm.cs.HANDOFF_FIXED_MESSAGE
    assert result["debug"]["next_action_reason"] == rag_debug["reason"]

    notify_admins_mock.assert_awaited_once()
    assert notify_admins_mock.await_args.kwargs["reason"] == rag_debug["reason"]
