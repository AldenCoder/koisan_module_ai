from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

from app.api.dependencies.time import VN_TZ, now_vn
from app.api.schemas.process_message import (
    ProcessMessageRequest,
    ProcessMessageResponse,
)
from app.api.schemas.slot_question import (
    SlotQuestionGenerationRequest,
    SlotQuestionGenerationResponse,
)
from app.models.branches import Branch
from app.models.messages import Message
from app.models.state_asked_slots import StateAskedSlot
from app.services import conversation_service as cs
from app.services.conversation_service import (
    create_conversation_service,
    generate_slot_question_service,
    get_conversation_by_id_service,
    get_latest_conversation_by_customer_name_service,
    update_conversation_profile_service,
)
from logs.logging_config import logger

router = APIRouter()


def _to_vn_aware_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=VN_TZ)
    return value.astimezone(VN_TZ)


async def run_response_message_flow(
    *,
    text: str,
    conversation_id: Optional[str],
    channel: Optional[str],
    customer_name: Optional[str],
    extracted_branch_name: Optional[str],
    extracted_intent: Optional[str],
    extracted_branch: Optional[str],
    extracted_slots: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    logger.info(
        "API_RESPONSE_MESSAGE_REQUEST payload=%s",
        cs._safe_json_dumps(
            {
                "text": text,
                "extracted_branch_name": extracted_branch_name or extracted_branch,
                "extracted_intent": extracted_intent,
                "extracted_slots": extracted_slots,
            }
        ),
    )

    conversation = await get_conversation_by_id_service(conversation_id)
    if conversation is None:
        conversation = await get_latest_conversation_by_customer_name_service(customer_name)

    if conversation is None:
        conversation = await create_conversation_service(
            channel=channel,
            customer_name=customer_name,
            customer_id=None,
        )
    else:
        conversation = await update_conversation_profile_service(
            conversation,
            channel=channel,
            customer_name=customer_name,
            customer_id=None,
        )

    intent = (extracted_intent or "").strip()
    if not intent:
        raise ValueError("response-message requires intent from /extract-intent.")
    intent_raw = "provided_by_extract_intent"

    state = await cs._get_previous_state(conversation.id)
    if not state:
        raise ValueError("No conversation state found. Call /extract-branch and /extract-slots state step before /response-message.")

    branch_doc = await Branch.get(state.branch_id)
    if not branch_doc:
        raise ValueError("Branch not found for current conversation state.")

    resolved_branch_id = state.branch_id
    resolved_branch_name = branch_doc.name

    provided_branch_name = (extracted_branch_name or extracted_branch or "").strip()
    if provided_branch_name:
        normalized_branch_name = provided_branch_name
        if normalized_branch_name and normalized_branch_name != resolved_branch_name:
            raise ValueError("branch does not match the latest conversation state")

    logger.info("STEP_01_LOAD_CONTEXT conversation_id=%s state_id=%s", conversation.id, state.id)
    user_message: Optional[Message] = None
    if state.message_id:
        existing_state_message = await Message.get(state.message_id)
        if (
            existing_state_message
            and (existing_state_message.role or "").strip().lower() == "user"
            and (existing_state_message.content or "").strip() == text.strip()
        ):
            user_message = existing_state_message

    if user_message is None:
        latest_user_message = await Message.find(
            {
                "conversation_id": conversation.id,
                "role": "user",
            }
        ).sort(-Message.created_at).first_or_none()
        latest_created_at = _to_vn_aware_datetime(
            latest_user_message.created_at if latest_user_message else None
        )
        if (
            latest_user_message
            and (latest_user_message.content or "").strip() == text.strip()
            and latest_created_at
            and (now_vn() - latest_created_at) <= timedelta(minutes=2)
        ):
            user_message = latest_user_message

    if user_message is None:
        user_message = Message(
            conversation_id=conversation.id,
            role="user",
            content=text,
            meta={
                "state_id": str(state.id),
                "source": "response-message",
            },
            created_at=now_vn(),
            updated_at=now_vn(),
        )
        await user_message.insert()

    state.message_id = user_message.id

    logger.info("STEP_02_MERGE_SLOT_VALUES conversation_id=%s state_id=%s", conversation.id, state.id)
    merged_slots = await cs._get_state_slots_map(state.id)
    asked_slots = await cs._get_state_asked_slots(state.id)
    missing_rows = await cs._get_state_missing_slots(state.id)

    previous_slot = (state.next_slot or "").strip() or None
    state.prev_slot = previous_slot

    extracted_slots_from_text = extracted_slots if isinstance(extracted_slots, dict) else {}
    matched_missing_slots: list[str] = []
    asked_slot_set = {
        slot for slot in asked_slots if slot and cs._has_slot_value(merged_slots.get(slot))
    }

    for row in missing_rows:
        slot_name = (row.slot_catalog_name or "").strip()
        if not slot_name:
            continue
        extracted_value = extracted_slots_from_text.get(slot_name)
        if not cs._has_slot_value(extracted_value):
            continue

        await cs._upsert_state_slot_value(state.id, slot_name, extracted_value)
        await row.delete()
        matched_missing_slots.append(slot_name)
        if cs._has_slot_value(extracted_value):
            asked_slot_set.add(slot_name)
        merged_slots[slot_name] = extracted_value

    if previous_slot:
        prev_value = extracted_slots_from_text.get(previous_slot)
        if cs._has_slot_value(prev_value):
            await cs._upsert_state_slot_value(state.id, previous_slot, prev_value)
            merged_slots[previous_slot] = prev_value
            asked_slot_set.add(previous_slot)

    if matched_missing_slots:
        logger.info(
            "STEP_02_SLOT_VALUES_UPDATED conversation_id=%s state_id=%s matched_slots=%s",
            conversation.id,
            state.id,
            matched_missing_slots,
        )

    missing_rows = await cs._get_state_missing_slots(state.id)
    unresolved_missing_ranked: list[tuple[int, int, int, str]] = []
    for idx, row in enumerate(missing_rows):
        slot_name = (row.slot_catalog_name or "").strip()
        if not slot_name:
            continue
        if cs._has_slot_value(merged_slots.get(slot_name)):
            continue
        unresolved_missing_ranked.append(
            (
                cs._priority_rank(row.priority),
                cs._to_int_or_default(row.sort_order, 999999),
                idx,
                slot_name,
            )
        )

    missing_slots = [item[3] for item in sorted(unresolved_missing_ranked)]
    asked_slot_set = {
        slot for slot in asked_slot_set if slot and cs._has_slot_value(merged_slots.get(slot))
    }
    asked_slots = list(dict.fromkeys(sorted(asked_slot_set)))
    recent_conversation_history = await cs._get_recent_conversation_history(conversation.id, limit=5)
    resolved_rag_anchor = cs.extract_rag_anchor(
        current_user_message=text,
        current_intent=intent,
        previous_next_slot=previous_slot,
        current_slots=extracted_slots_from_text,
        recent_conversation_history=recent_conversation_history,
        stored_rag_anchor=state.rag_anchor_text,
    )
    if not (state.rag_anchor_text or "").strip():
        state.rag_anchor_text = resolved_rag_anchor or state.rag_anchor_text

    logger.info("STEP_03_DECIDE_ACTION conversation_id=%s state_id=%s", conversation.id, state.id)
    next_action, next_slot, next_action_reason = cs.decide_next_action_service(
        missing_slots=missing_slots,
        slots=merged_slots,
    )
    next_action_raw = "rule_based"

    assistant_message = None
    ask_slot_prompt_raw = ""
    action_response_raw = ""
    admin_notify_debug: Dict[str, Any] = {}

    if next_action == "ask_slot" and next_slot:
        logger.info("STEP_04_ASK_SLOT conversation_id=%s state_id=%s slot=%s", conversation.id, state.id, next_slot)
        question_result = await generate_slot_question_service(
            slot_name=next_slot,
            branch=resolved_branch_name,
            intent=intent,
            known_slots=merged_slots,
            user_text=text,
            customer_name=conversation.customer_name,
            conversation_id=str(conversation.id),
            asked_slot_values=cs._build_asked_slot_values(asked_slots, merged_slots),
        )
        assistant_message = question_result.get("question")
        ask_slot_prompt_raw = question_result.get("raw_response", "")
    elif next_action == "call_rag":
        logger.info("STEP_04_CALL_RAG conversation_id=%s state_id=%s", conversation.id, state.id)
        rag_request_payload = await cs._build_rag_payload(
            latest_user_message=text,
            branch=resolved_branch_name,
            slots=merged_slots,
            conversation_id=conversation.id,
            current_intent=intent,
            previous_next_slot=previous_slot,
            current_slots=extracted_slots_from_text,
            stored_rag_anchor=state.rag_anchor_text,
            recent_conversation_history=recent_conversation_history,
        )
        logger.info(
            "STEP_04_CALL_RAG_REQUEST conversation_id=%s state_id=%s payload=%s",
            conversation.id,
            state.id,
            cs._safe_json_dumps(cs._sanitize_rag_payload_for_log(rag_request_payload)),
        )
        rag_answer, rag_debug = await cs.call_rag_service(
            latest_user_message=text,
            branch=resolved_branch_name,
            intent=intent,
            slots=merged_slots,
            conversation_id=conversation.id,
            prebuilt_payload=rag_request_payload,
            customer_name=conversation.customer_name,
            customer_id=conversation.customer_id,
            channel=conversation.channel,
        )
        logger.info(
            "STEP_04_CALL_RAG_RESPONSE conversation_id=%s state_id=%s response=%s",
            conversation.id,
            state.id,
            cs._safe_json_dumps(
                cs._build_rag_response_log_snapshot(answer=rag_answer, debug=rag_debug)
            ),
        )
        action_response_raw = cs._safe_json_dumps(rag_debug)
        if rag_answer:
            assistant_message = rag_answer
        else:
            next_action = "handoff"
            next_slot = None
            next_action_reason = str(rag_debug.get("reason") or "rag_no_data_found")
            next_action_raw = cs._safe_json_dumps(rag_debug)
            assistant_message = cs.HANDOFF_FIXED_MESSAGE
            admin_notify_debug = await cs._notify_handoff_admins(
                conversation=conversation,
                intent=intent,
                branch=resolved_branch_name,
                latest_user_message=text,
                slots=merged_slots,
                reason=next_action_reason,
            )
    elif next_action == "handoff":
        assistant_message = cs.HANDOFF_FIXED_MESSAGE
        admin_notify_debug = await cs._notify_handoff_admins(
            conversation=conversation,
            intent=intent,
            branch=resolved_branch_name,
            latest_user_message=text,
            slots=merged_slots,
            reason=next_action_reason or "handoff_requested",
        )

    logger.info("STEP_05_PERSIST_RESPONSE conversation_id=%s state_id=%s action=%s", conversation.id, state.id, next_action)
    asked_slots = [
        slot for slot in dict.fromkeys(asked_slots) if cs._has_slot_value(merged_slots.get(slot))
    ]

    state.intent = intent
    state.next_action = next_action
    state.prev_slot = previous_slot
    state.next_slot = next_slot
    state.updated_at = now_vn()
    await state.save()

    await StateAskedSlot.find(StateAskedSlot.conversation_state_id == state.id).delete()
    for slot_name in asked_slots:
        asked = StateAskedSlot(
            conversation_state_id=state.id,
            slot_catalog_name=slot_name,
            created_at=now_vn(),
            updated_at=now_vn(),
        )
        await asked.insert()

    if assistant_message:
        existing_bot_message = await Message.find_one(
            {
                "conversation_id": conversation.id,
                "role": "bot",
                "meta.reply_to_message_id": str(user_message.id),
            }
        )
        if not existing_bot_message:
            bot_message = Message(
                conversation_id=conversation.id,
                role="bot",
                content=assistant_message,
                meta={
                    "state_id": str(state.id),
                    "action": next_action,
                    "slot": next_slot,
                    "reply_to_message_id": str(user_message.id),
                },
                created_at=now_vn(),
                updated_at=now_vn(),
            )
            await bot_message.insert()

    conversation.updated_at = now_vn()
    await conversation.save()

    conversation_detail = await cs._build_conversation_detail(conversation)
    return {
        "conversation_id": str(conversation.id),
        "message_id": str(state.message_id),
        "state_id": str(state.id),
        "state": {
            "branch_id": str(resolved_branch_id),
            "branch": resolved_branch_name,
            "intent": intent,
            "rag_anchor_text": state.rag_anchor_text,
            "slots": merged_slots,
            "missing_slots": missing_slots,
            "asked_slots": asked_slots,
            "next_action": next_action,
            "prev_slot": previous_slot,
            "next_slot": next_slot,
        },
        "assistant_message": assistant_message,
        "conversation_detail": conversation_detail,
        "debug": {
            "intent_raw": intent_raw,
            "branch_raw": "resolved_from_latest_state",
            "next_action_reason": next_action_reason,
            "next_action_raw": next_action_raw,
            "ask_slot_prompt_raw": ask_slot_prompt_raw,
            "action_response_raw": action_response_raw,
            "admin_notify": admin_notify_debug,
        },
    }


@router.post("/response-message", response_model=ProcessMessageResponse)
async def response_message(payload: ProcessMessageRequest) -> ProcessMessageResponse:
    try:
        result = await run_response_message_flow(
            text=payload.text,
            conversation_id=payload.conversation_id,
            channel=payload.channel,
            customer_name=payload.customer_name,
            extracted_branch_name=payload.branch,
            extracted_intent=payload.intent,
            extracted_branch=payload.branch,
            extracted_slots=payload.extracted_slots,
        )
        return ProcessMessageResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Error in /response-message: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to process message") from exc


@router.post("/generate-slot-question", response_model=SlotQuestionGenerationResponse)
async def generate_slot_question(
    payload: SlotQuestionGenerationRequest,
) -> SlotQuestionGenerationResponse:
    try:
        result = await generate_slot_question_service(
            slot_name=payload.slot_name,
            branch=payload.branch,
            intent=payload.intent,
            known_slots=payload.known_slots,
            user_text=payload.user_text,
            customer_name=payload.customer_name,
            conversation_id=payload.conversation_id,
        )
        return SlotQuestionGenerationResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Error in /generate-slot-question: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to generate slot question") from exc
