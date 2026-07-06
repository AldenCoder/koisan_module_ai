from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from pydantic_core import ValidationError as PydanticCoreValidationError

from app.api.dependencies.time import now_vn
from app.models.branch_slots import BranchSlot
from app.models.conversation_states import ConversationState
from app.models.conversations import Conversation
from app.models.messages import Message
from app.models.state_asked_slots import StateAskedSlot
from app.models.state_missing_slots import StateMissingSlot
from app.models.state_slots import StateSlot
from app.models.slot_catalog import SlotCatalog
from app.services.ai_service import detect_slots
from app.services.catalog_service import ensure_branch_and_slots_for_name, get_slot_definition
from logs.logging_config import logger


def _safe_json_dumps(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, default=str)
    except Exception:
        return str(data)


def _to_slot_value(slot_value: Any) -> str:
    if slot_value is None:
        return ""
    if isinstance(slot_value, list):
        return ", ".join(str(item) for item in slot_value)
    if isinstance(slot_value, dict):
        return str(slot_value)
    return str(slot_value)


def _has_slot_value(slot_value: Any) -> bool:
    if slot_value is None:
        return False
    if isinstance(slot_value, str):
        return bool(slot_value.strip())
    if isinstance(slot_value, list):
        return len(slot_value) > 0
    return True


def _priority_rank(priority: Optional[str]) -> int:
    normalized = (priority or "").strip().lower()
    if normalized == "high":
        return 0
    if normalized == "medium":
        return 1
    if normalized == "low":
        return 2
    return 9


def _to_int_or_default(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _should_skip_missing_slot(slot_name: str, slots: Dict[str, Any]) -> bool:
    normalized_slot = (slot_name or "").strip().lower()
    if normalized_slot != "prewedding_outdoor_location":
        return False

    shoot_type = str(slots.get("prewedding_shoot_type") or "").strip().lower()
    if not shoot_type:
        return False

    has_studio = "studio" in shoot_type
    has_outdoor_or_mix = any(
        token in shoot_type
        for token in ["ngoại", "ngoai", "outdoor", "kết hợp", "ket hop", "both", "cả hai", "ca hai"]
    )
    return has_studio and not has_outdoor_or_mix


def _decide_next_action_for_state(
    *,
    missing_slots: List[str],
    slots: Dict[str, Any],
) -> tuple[Optional[str], Optional[str], str]:
    if missing_slots:
        return "ask_slot", missing_slots[0], "missing_slot_detected"

    return "call_rag", None, "no_missing_slot_call_rag"


async def _get_previous_state(conversation_id) -> Optional[ConversationState]:
    return await ConversationState.find(
        {
            "conversation_id": conversation_id,
            "branch_id": {"$exists": True},
        }
    ).sort(-ConversationState.updated_at).first_or_none()


async def _get_state_slots_map(state_id) -> Dict[str, Any]:
    rows = await StateSlot.find(StateSlot.conversation_state_id == state_id).to_list()
    slots: Dict[str, Any] = {}
    for row in rows:
        if row.slot_catalog_name:
            slots[row.slot_catalog_name] = row.slot_value_json.get("value", row.slot_value)
    return slots


async def _get_state_asked_slots(state_id) -> List[str]:
    rows = await StateAskedSlot.find(StateAskedSlot.conversation_state_id == state_id).to_list()
    result: List[str] = []
    for row in rows:
        if row.slot_catalog_name:
            result.append(row.slot_catalog_name)
    return result


async def _get_conversation_slot_memory(conversation_id) -> Dict[str, Any]:
    states = await ConversationState.find(
        ConversationState.conversation_id == conversation_id
    ).to_list()
    if not states:
        return {}

    state_ids = [state.id for state in states if state.id]
    if not state_ids:
        return {}

    rows = await StateSlot.find(
        {"conversation_state_id": {"$in": state_ids}}
    ).sort(-StateSlot.updated_at).to_list()

    slot_memory: Dict[str, Any] = {}
    for row in rows:
        slot_name = (row.slot_catalog_name or "").strip()
        if not slot_name or slot_name in slot_memory:
            continue
        slot_value = row.slot_value_json.get("value", row.slot_value)
        if not _has_slot_value(slot_value):
            continue
        slot_memory[slot_name] = slot_value

    return slot_memory


def _merge_slot_memory_into_extracted_slots(
    *,
    extracted_slots_map: Dict[str, Any],
    slot_memory: Dict[str, Any],
    allowed_slot_names: set[str],
) -> Dict[str, Any]:
    for slot_name in allowed_slot_names:
        if _has_slot_value(extracted_slots_map.get(slot_name)):
            continue
        memory_value = slot_memory.get(slot_name)
        if _has_slot_value(memory_value):
            extracted_slots_map[slot_name] = memory_value
    return extracted_slots_map


async def extract_slots_service(
    *,
    text: str,
    intent: Optional[str],
    branch_hint: Optional[str],
) -> Dict[str, Any]:
    slot_items, confidence, raw = await detect_slots(
        text=text,
        intent=intent,
        branch_name=branch_hint,
    )
    slot_map: Dict[str, Any] = {}
    primary_slot: Optional[str] = None
    primary_value: Any = None
    best_conf = -1.0

    for item in slot_items:
        slot_name = str(item.get("slot") or "").strip()
        slot_value = item.get("value")
        if not slot_name or not _has_slot_value(slot_value):
            continue
        slot_map[slot_name] = slot_value
        conf_value = item.get("confidence", 0.0)
        if isinstance(conf_value, str):
            try:
                conf_value = float(conf_value)
            except Exception:
                conf_value = 0.0
        if not isinstance(conf_value, (int, float)):
            conf_value = 0.0
        conf_value = max(0.0, min(1.0, float(conf_value)))
        if conf_value > best_conf:
            best_conf = conf_value
            primary_slot = slot_name
            primary_value = slot_value

    return {
        "slot": primary_slot,
        "value": primary_value,
        "confidence": float(confidence),
        "slots": slot_map,
        "raw_response": raw,
    }


async def update_branch_slot_state_service(
    *,
    text: str,
    intent: str,
    message_id: str,
    conversation_id: Optional[str],
    branch_name: Optional[str],
    slots: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
    raw_response: str = "",
) -> Dict[str, Any]:
    context = await prepare_update_slot_state_service(
        text=text,
        intent=intent,
        message_id=message_id,
        conversation_id=conversation_id,
        branch_name=branch_name,
        slots=slots,
        metadata=metadata,
        raw_response=raw_response,
    )
    return await persist_update_slot_state_service(context)


async def prepare_update_slot_state_service(
    *,
    text: str,
    intent: str,
    message_id: str,
    conversation_id: Optional[str],
    branch_name: Optional[str],
    slots: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
    raw_response: str = "",
) -> Dict[str, Any]:
    logger.info(
        "API_UPDATE_BRANCH_SLOT_STATE_REQUEST payload=%s",
        _safe_json_dumps(
            {
                "text": text,
                "intent": intent,
                "message_id": message_id,
                "conversation_id": conversation_id,
                "branch_name": branch_name,
                "slots": slots,
                "metadata": metadata,
            }
        ),
    )

    try:
        existing_message = await Message.get(message_id)
    except (ValueError, TypeError, PydanticCoreValidationError) as exc:
        raise ValueError("Invalid message_id format") from exc

    if not existing_message:
        raise ValueError("message_id not found")

    conversation = await Conversation.get(existing_message.conversation_id)
    if not conversation:
        raise ValueError("Conversation not found for message_id")

    if conversation_id:
        normalized_conversation_id = conversation_id.strip()
        if normalized_conversation_id and normalized_conversation_id != str(conversation.id):
            raise ValueError("conversation_id does not match message_id")

    if metadata:
        existing_message.meta = {**(existing_message.meta or {}), **metadata}
        existing_message.updated_at = now_vn()
        await existing_message.save()

    resolved_branch_name = (branch_name or "").strip() or None
    branch_id = None
    resolved_branch_object_id = None
    if resolved_branch_name:
        branch_doc = await ensure_branch_and_slots_for_name(resolved_branch_name)
        branch_id = str(branch_doc.id)
        resolved_branch_object_id = branch_doc.id

    extracted_slot_names = list(slots.keys())
    slot_docs = (
        await SlotCatalog.find({"name": {"$in": extracted_slot_names}}).to_list()
        if extracted_slot_names
        else []
    )
    slot_doc_map = {doc.name: doc for doc in slot_docs if doc.name}

    normalized_slots: List[Dict[str, Any]] = []
    for slot_name, slot_value in slots.items():
        slot_doc = slot_doc_map.get(slot_name)
        if not slot_doc:
            continue

        applies_to = [
            str(item or "").strip()
            for item in (slot_doc.applies_to or [])
            if str(item or "").strip()
        ]
        if (
            resolved_branch_name
            and applies_to
            and "all" not in applies_to
            and resolved_branch_name not in applies_to
        ):
            continue

        normalized_slots.append(
            {
                "slot_id": str(slot_doc.id),
                "slot_name": slot_doc.name,
                "slot_value": slot_value,
            }
        )

    extracted_slots_map = {
        slot_item["slot_name"]: slot_item["slot_value"]
        for slot_item in normalized_slots
        if slot_item.get("slot_name")
    }

    resolved_branch_id = resolved_branch_object_id
    if not resolved_branch_id:
        raise ValueError("Unable to determine branch_id for state creation.")

    previous_state = await _get_previous_state(conversation.id)
    previous_slots_map: Dict[str, Any] = {}
    previous_asked_slots: List[str] = []
    previous_next_slot: Optional[str] = None
    if previous_state:
        previous_next_slot = (previous_state.next_slot or "").strip() or None
        previous_slots_map = await _get_state_slots_map(previous_state.id)
        previous_asked_slots = await _get_state_asked_slots(previous_state.id)

    if previous_state and previous_state.branch_id == resolved_branch_id:
        for previous_slot_name, previous_slot_value in previous_slots_map.items():
            if not _has_slot_value(previous_slot_value):
                continue
            if _has_slot_value(extracted_slots_map.get(previous_slot_name)):
                continue
            extracted_slots_map[previous_slot_name] = previous_slot_value

    branch_slots = await BranchSlot.find(
        {"branch_id": resolved_branch_id}
    ).sort(BranchSlot.sort_order).to_list()
    branch_slot_names = {
        row.slot_catalog_name
        for row in branch_slots
        if row.slot_catalog_name
    }
    conversation_slot_memory = await _get_conversation_slot_memory(conversation.id)
    extracted_slots_map = _merge_slot_memory_into_extracted_slots(
        extracted_slots_map=extracted_slots_map,
        slot_memory=conversation_slot_memory,
        allowed_slot_names=branch_slot_names,
    )

    asked_slots = list(dict.fromkeys(previous_asked_slots))
    missing_slots: List[str] = []
    for branch_slot in branch_slots:
        slot_name = branch_slot.slot_catalog_name
        if not slot_name:
            continue
        if _has_slot_value(extracted_slots_map.get(slot_name)):
            if slot_name not in asked_slots:
                asked_slots.append(slot_name)
        else:
            missing_slots.append(slot_name)

    answered_previous_next_slot = False
    if previous_next_slot:
        answered_previous_next_slot = _has_slot_value(extracted_slots_map.get(previous_next_slot))
        logger.info(
            "WEBHOOK_SLOT_ANSWER_CHECK conversation_id=%s previous_next_slot=%s answered=%s",
            str(conversation.id),
            previous_next_slot,
            answered_previous_next_slot,
        )
        if answered_previous_next_slot and previous_next_slot not in asked_slots:
            asked_slots.append(previous_next_slot)

    missing_rows_ranked: List[tuple[int, int, int, str]] = []
    branch_slot_map = {row.slot_catalog_name: row for row in branch_slots if row.slot_catalog_name}
    for idx, slot_name in enumerate(missing_slots):
        branch_slot = branch_slot_map.get(slot_name)
        slot_def = get_slot_definition(slot_name) or {}
        missing_rows_ranked.append(
            (
                _priority_rank(slot_def.get("priority")),
                _to_int_or_default(branch_slot.sort_order if branch_slot else None, 999999),
                idx,
                slot_name,
            )
        )

    missing_slots = [item[3] for item in sorted(missing_rows_ranked)]
    asked_slots = [
        slot for slot in dict.fromkeys(asked_slots) if _has_slot_value(extracted_slots_map.get(slot))
    ]

    next_action, next_slot, _next_action_reason = _decide_next_action_for_state(
        missing_slots=missing_slots,
        slots=extracted_slots_map,
    )

    return {
        "intent": intent,
        "message_id": message_id,
        "raw_response": raw_response,
        "conversation": conversation,
        "existing_message": existing_message,
        "branch_id": branch_id,
        "resolved_branch_name": resolved_branch_name,
        "resolved_branch_id": resolved_branch_id,
        "normalized_slots": normalized_slots,
        "extracted_slots_map": extracted_slots_map,
        "previous_state": previous_state,
        "previous_next_slot": previous_next_slot,
        "branch_slots": branch_slots,
        "asked_slots": asked_slots,
        "missing_slots": missing_slots,
        "next_action": next_action,
        "next_slot": next_slot,
    }


async def persist_update_slot_state_service(context: Dict[str, Any]) -> Dict[str, Any]:
    intent = str(context.get("intent") or "")
    raw_response = str(context.get("raw_response") or "")
    conversation: Conversation = context["conversation"]
    existing_message: Message = context["existing_message"]
    branch_id: Optional[str] = context.get("branch_id")
    resolved_branch_name: Optional[str] = context.get("resolved_branch_name")
    resolved_branch_id = context["resolved_branch_id"]
    normalized_slots: List[Dict[str, Any]] = context.get("normalized_slots", [])
    extracted_slots_map: Dict[str, Any] = context.get("extracted_slots_map", {})
    previous_state: Optional[ConversationState] = context.get("previous_state")
    previous_next_slot: Optional[str] = context.get("previous_next_slot")
    branch_slots: List[BranchSlot] = context.get("branch_slots", [])
    asked_slots: List[str] = context.get("asked_slots", [])
    missing_slots: List[str] = context.get("missing_slots", [])
    next_action: Optional[str] = context.get("next_action")
    next_slot: Optional[str] = context.get("next_slot")

    reuse_previous_state = bool(
        previous_state
        and previous_state.branch_id == resolved_branch_id
    )

    if reuse_previous_state:
        state = previous_state
        # Requirement: with same branch_id and next_action, update state in-place.
        state.message_id = existing_message.id
        state.intent = intent
        state.prev_slot = previous_next_slot
        state.next_slot = next_slot
        state.updated_at = now_vn()
        await state.save()
    else:
        state = ConversationState(
            conversation_id=conversation.id,
            message_id=existing_message.id,
            branch_id=resolved_branch_id,
            intent=intent,
            turn_index=str(
                await ConversationState.find(
                    ConversationState.conversation_id == conversation.id
                ).count()
                + 1
            ),
            next_action=next_action,
            prev_slot=previous_next_slot,
            next_slot=next_slot,
            rag_anchor_text=(
                previous_state.rag_anchor_text
                if previous_state and (previous_state.rag_anchor_text or "").strip()
                else (existing_message.content or "").strip()
            ),
            created_at=now_vn(),
            updated_at=now_vn(),
        )
        await state.insert()

    existing_state_slots = await StateSlot.find(
        StateSlot.conversation_state_id == state.id
    ).to_list()
    branch_slot_map = {row.slot_catalog_name: row for row in branch_slots if row.slot_catalog_name}
    existing_state_slot_map: Dict[str, StateSlot] = {}
    for row in existing_state_slots:
        slot_name = row.slot_catalog_name
        if not slot_name:
            continue
        if slot_name in existing_state_slot_map:
            # Keep one row per slot_name and remove duplicated leftovers.
            await row.delete()
            continue
        existing_state_slot_map[slot_name] = row

    branch_slot_names = {
        row.slot_catalog_name
        for row in branch_slots
        if row.slot_catalog_name
    }
    processed_slot_names: set[str] = set()

    for branch_slot in branch_slots:
        slot_name = branch_slot.slot_catalog_name
        if not slot_name or slot_name in processed_slot_names:
            continue
        processed_slot_names.add(slot_name)

        slot_value = extracted_slots_map.get(slot_name)
        if slot_name in existing_state_slot_map:
            row = existing_state_slot_map[slot_name]
            row.slot_value = _to_slot_value(slot_value) if _has_slot_value(slot_value) else None
            row.slot_value_json = {"value": slot_value}
            row.updated_at = now_vn()
            await row.save()
            continue

        inserted_row = StateSlot(
            conversation_state_id=state.id,
            slot_catalog_name=slot_name,
            slot_value=_to_slot_value(slot_value) if _has_slot_value(slot_value) else None,
            slot_value_json={"value": slot_value},
            created_at=now_vn(),
            updated_at=now_vn(),
        )
        await inserted_row.insert()
        existing_state_slot_map[slot_name] = inserted_row

    for row in existing_state_slots:
        if row.slot_catalog_name and row.slot_catalog_name not in branch_slot_names:
            await row.delete()

    await StateMissingSlot.find(StateMissingSlot.conversation_state_id == state.id).delete()
    slot_catalog_docs = (
        await SlotCatalog.find({"name": {"$in": missing_slots}}).to_list()
        if missing_slots
        else []
    )
    slot_priority_map = {doc.name: doc.priority for doc in slot_catalog_docs if doc.name}

    for slot_name in missing_slots:
        branch_slot = branch_slot_map.get(slot_name)
        missing = StateMissingSlot(
            conversation_state_id=state.id,
            slot_catalog_name=slot_name,
            priority=slot_priority_map.get(slot_name),
            sort_order=str(branch_slot.sort_order) if branch_slot and branch_slot.sort_order is not None else None,
            created_at=now_vn(),
            updated_at=now_vn(),
        )
        await missing.insert()

    await StateAskedSlot.find(StateAskedSlot.conversation_state_id == state.id).delete()
    for slot_name in asked_slots:
        asked = StateAskedSlot(
            conversation_state_id=state.id,
            slot_catalog_name=slot_name,
            created_at=now_vn(),
            updated_at=now_vn(),
        )
        await asked.insert()

    conversation.updated_at = now_vn()
    await conversation.save()

    first_slot = normalized_slots[0] if normalized_slots else None
    result = {
        "conversation_id": str(conversation.id),
        "state_id": str(state.id),
        "branch_id": branch_id,
        "branch_name": resolved_branch_name,
        "slot_id": first_slot.get("slot_id") if first_slot else None,
        "slot_name": first_slot.get("slot_name") if first_slot else None,
        "slots": extracted_slots_map,
        "raw_response": raw_response,
    }

    logger.info("API_UPDATE_BRANCH_SLOT_STATE_RESPONSE payload=%s", _safe_json_dumps(result))
    return result
