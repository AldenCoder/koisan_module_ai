import json

from fastapi import APIRouter, HTTPException

from app.api.dependencies.time import now_vn

from app.api.schemas.intent import IntentAnalysisRequest
from app.api.schemas.process_message import ProcessMessageResponse
from app.models.branches import Branch
from app.services.conversation_service import (
    build_conversation_detail_service,
    create_conversation_service,
    extract_intent_service,
    get_conversation_by_id_service,
    get_latest_conversation_by_customer_id_service,
    get_latest_conversation_by_customer_name_service,
    get_latest_state_service,
    get_state_snapshot_service,
    insert_bot_messages_service,
    update_conversation_profile_service,
)
from app.api.v1.response_message import run_response_message_flow
from app.services.branch_service import (
    extract_branch_service,
)
from app.services.slot_service import (
    extract_slots_service,
    update_branch_slot_state_service,
)
from logs.logging_config import logger

router = APIRouter()

FIXED_GREETING_MESSAGE = (
    "ẢNH CƯỚI NHA TRANG - Xoài Weddings xin chào anh/chị Quynh Anh . "
    "Dạ mình gửi cho em SĐT hoặc số Zalo để nhân viên tư vấn sẽ gửi thông tin cũng như chương trình ưu đãi "
    "(nếu có) sớm, để mình tiện tham khảo và đưa ra sự lựa chọn phù hợp nhé ạ 🥰"
)
DEFAULT_GREETING_BRANCH = "greeting_initial_qualification"


async def _build_fixed_response(
    *,
    conversation,
    message_id: str,
    intent: str,
    fixed_message: str,
    state,
):
    branch_doc = await Branch.get(state.branch_id)
    state_snapshot = await get_state_snapshot_service(state.id)
    await insert_bot_messages_service(
        conversation_id=conversation.id,
        reply_to_message_id=message_id,
        messages=[fixed_message],
        state_id=str(state.id),
        action="fixed_reply",
        slot=None,
    )
    conversation.updated_at = now_vn()
    await conversation.save()
    conversation_detail = await build_conversation_detail_service(conversation)
    return {
        "conversation_id": str(conversation.id),
        "message_id": str(message_id),
        "state_id": str(state.id),
        "state": {
            "branch_id": str(state.branch_id),
            "branch": branch_doc.name if branch_doc else None,
            "intent": intent,
            "slots": state_snapshot.get("slots", {}),
            "missing_slots": state_snapshot.get("missing_slots", []),
            "asked_slots": state_snapshot.get("asked_slots", []),
            "next_action": state.next_action,
            "prev_slot": state.prev_slot,
            "next_slot": state.next_slot,
        },
        "assistant_message": fixed_message,
        "conversation_detail": conversation_detail,
        "debug": {
            "intent_raw": "fixed_reply",
            "branch_raw": "fixed_reply",
            "next_action_reason": "fixed_reply",
            "next_action_raw": "fixed_reply",
            "ask_slot_prompt_raw": "",
            "action_response_raw": "",
            "admin_notify": {},
        },
    }


def _safe_json(value):
    try:
        if hasattr(value, "model_dump"):
            return json.dumps(value.model_dump(mode="json"), ensure_ascii=False, default=str)
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


@router.post("/total-response", response_model=ProcessMessageResponse)
async def workflow_total_response(payload: IntentAnalysisRequest) -> ProcessMessageResponse:
    try:
        logger.info("WORKFLOW_TOTAL_REQUEST payload=%s", _safe_json(payload))

        # STEP 1: extract intent (and create initial user message)
        conversation = await get_conversation_by_id_service(payload.conversation_id)
        if conversation is None:
            conversation = await get_latest_conversation_by_customer_id_service(payload.customer_id)
        if conversation is None:
            conversation = await get_latest_conversation_by_customer_name_service(payload.customer_name)

        if conversation is None:
            conversation = await create_conversation_service(
                channel=payload.channel,
                customer_name=payload.customer_name,
                customer_id=payload.customer_id,
            )
        else:
            conversation = await update_conversation_profile_service(
                conversation,
                channel=payload.channel,
                customer_name=payload.customer_name,
                customer_id=payload.customer_id,
            )

        step_1 = await extract_intent_service(
            text=payload.text,
            conversation=conversation,
            message_mid=payload.message_mid,
            metadata=payload.metadata,
        )

        intent = step_1.get("intent")
        history_count = int(step_1.get("history_count") or 0)
        is_new_conversation = history_count == 0

        if intent in {"greeting", "other"}:
            if is_new_conversation:
                await update_branch_slot_state_service(
                    text=payload.text,
                    intent=step_1["intent"],
                    message_id=step_1["message_id"],
                    conversation_id=step_1["conversation_id"],
                    branch_name=DEFAULT_GREETING_BRANCH,
                    slots={},
                    metadata=payload.metadata,
                    raw_response=_safe_json(
                        {
                            "branch_raw": "fixed_reply",
                            "slots_raw": "fixed_reply",
                        }
                    ),
                )
                state = await get_latest_state_service(conversation.id)
                if not state:
                    raise ValueError("No conversation state found for fixed reply.")
                step_2 = await _build_fixed_response(
                    conversation=conversation,
                    message_id=step_1["message_id"],
                    intent=step_1["intent"],
                    fixed_message=FIXED_GREETING_MESSAGE,
                    state=state,
                )
                return ProcessMessageResponse(**step_2)

            if intent == "greeting":
                state = await get_latest_state_service(conversation.id)
                if not state:
                    await update_branch_slot_state_service(
                        text=payload.text,
                        intent=step_1["intent"],
                        message_id=step_1["message_id"],
                        conversation_id=step_1["conversation_id"],
                        branch_name=DEFAULT_GREETING_BRANCH,
                        slots={},
                        metadata=payload.metadata,
                        raw_response=_safe_json(
                            {
                                "branch_raw": "fixed_reply",
                                "slots_raw": "fixed_reply",
                            }
                        ),
                    )
                    state = await get_latest_state_service(conversation.id)
                if not state:
                    raise ValueError("No conversation state found for fixed reply.")
                customer_name = (conversation.customer_name or payload.customer_name or "").strip()
                if customer_name:
                    reply_text = f"Anh/chị {customer_name} cần hỗ trợ gì thêm ko ạ!"
                else:
                    reply_text = "Anh/chị cần hỗ trợ gì thêm ko ạ!"
                step_2 = await _build_fixed_response(
                    conversation=conversation,
                    message_id=step_1["message_id"],
                    intent=step_1["intent"],
                    fixed_message=reply_text,
                    state=state,
                )
                return ProcessMessageResponse(**step_2)

            state = await get_latest_state_service(conversation.id)
            if not state:
                await update_branch_slot_state_service(
                    text=payload.text,
                    intent=step_1["intent"],
                    message_id=step_1["message_id"],
                    conversation_id=step_1["conversation_id"],
                    branch_name=DEFAULT_GREETING_BRANCH,
                    slots={},
                    metadata=payload.metadata,
                    raw_response=_safe_json(
                        {
                            "branch_raw": "fixed_reply",
                            "slots_raw": "fixed_reply",
                        }
                    ),
                )
            step_2 = await run_response_message_flow(
                text=payload.text,
                conversation_id=step_1["conversation_id"],
                channel=payload.channel,
                customer_name=payload.customer_name,
                extracted_branch_name=None,
                extracted_intent=step_1["intent"],
                extracted_branch=None,
                extracted_slots={},
            )
            return ProcessMessageResponse(**step_2)

        # STEP 2: detect branch.
        branch_hint_for_step = None
        latest_state = await get_latest_state_service(conversation.id)
        if latest_state and (latest_state.next_action or "").strip().lower() == "ask_slot":
            latest_branch = await Branch.get(latest_state.branch_id)
            if latest_branch and (latest_branch.name or "").strip():
                branch_hint_for_step = latest_branch.name

        step_branch = await extract_branch_service(
            text=payload.text,
            intent=intent,
            branch_hint=branch_hint_for_step,
        )

        # STEP 3: extract slot values for selected branch.
        step_slots = await extract_slots_service(
            text=payload.text,
            intent=intent,
            branch_hint=step_branch.get("branch_name"),
        )

        # STEP 4: update state from branch + slots.
        step_state = await update_branch_slot_state_service(
            text=payload.text,
            intent=intent,
            message_id=step_1["message_id"],
            conversation_id=step_1["conversation_id"],
            branch_name=step_branch.get("branch_name"),
            slots=step_slots.get("slots", {}),
            metadata=payload.metadata,
            raw_response=_safe_json(
                {
                    "branch_raw": step_branch.get("raw_response", ""),
                    "slots_raw": step_slots.get("raw_response", ""),
                }
            ),
        )
        logger.info("WORKFLOW_TOTAL_STEP_BRANCH_RESPONSE data=%s", _safe_json(step_state))

        # STEP 5: response-message flow.
        step_2 = await run_response_message_flow(
            text=payload.text,
            conversation_id=step_1["conversation_id"],
            channel=payload.channel,
            customer_name=payload.customer_name,
            extracted_branch_name=step_branch.get("branch_name"),
            extracted_intent=intent,
            extracted_branch=step_branch.get("branch_name"),
            extracted_slots=step_state.get("slots", {}),
        )
        # logger.info("WORKFLOW_TOTAL_STEP_2_RESPONSE data=%s", _safe_json(step_2))

        # Final response: return first response-message result to avoid duplicate GPT calls.
        return ProcessMessageResponse(**step_2)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Error in /workflow/total-response: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to run total workflow") from exc
