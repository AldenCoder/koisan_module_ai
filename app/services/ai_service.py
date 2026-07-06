import json
import os
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from openai import OpenAI

from app.models.branches import Branch
from app.models.slot_catalog import SlotCatalog
from app.services.catalog_service import get_slot_definition
from logs.logging_config import logger

ALLOWED_INTENTS = [
    "greeting",
    "provide_information",
    "ask_service_info",
    "price_request",
    "other",
]

load_dotenv()

_openai_client: OpenAI | None = None
_openai_client_api_key: str | None = None


INTENT_SYSTEM_PROMPT = """
You are an intent classifier for a wedding consultation chatbot.
The user payload is JSON with:
- current_message: latest user message
- history_last_5: up to 5 previous user messages (oldest -> newest)
- asked_slots: slots that were already asked in current conversation state
- missing_slots: slots still missing in current conversation state

Use both current_message and history_last_5 for classification, but prioritize current_message when conflict happens.
Use asked_slots and missing_slots as supportive workflow context only.
Return strictly valid JSON only:
{
  "intent": "one_of_allowed_intents",
  "confidence": 0.0
}
Allowed intents: greeting, provide_information, ask_service_info, price_request, other.
""".strip()


BRANCH_SYSTEM_PROMPT = """
You are a branch classifier for a wedding consultation chatbot.

Input payload JSON contains:
- intent: optional detected intent
- branch_hint: optional hint branch name
- text: latest user message
- branch_options: array of branches from database with fields name and label

Task:
- Choose exactly one best branch_name from branch_options based on user text.
- Prioritize user text, then intent, then branch_hint as supporting signal.
- Never create a branch name outside branch_options.

Return strictly valid JSON only:
{
    "branch": "branch_name_or_null",
    "confidence": 0.0
}
""".strip()


SLOT_SYSTEM_PROMPT = """
You are a slot extraction assistant for a wedding consultation chatbot.

Input payload JSON contains:
- intent: optional detected intent
- branch_name: selected branch name
- text: latest user message
- slot_options: array of slot definitions from database with fields name, label, description

Task:
- Extract only slot values that are explicitly present in text.
- Use only slot names that exist in slot_options.
- If no value found for a slot, do not output that slot.
- Do not infer missing values.

Return strictly valid JSON only as a JSON array (can be empty):
[
  {
    "slot": "slot_name_or_null",
    "value": "extracted_value",
    "confidence": 0.0
  }
]
""".strip()


def _get_openai_client() -> OpenAI:
    global _openai_client
    global _openai_client_api_key

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing. Please set it in environment.")

    if _openai_client is None or _openai_client_api_key != api_key:
        _openai_client = OpenAI(api_key=api_key)
        _openai_client_api_key = api_key

    return _openai_client


def _get_intent_model() -> str | None:
    return os.getenv("EXTRACT_INTENT_MODEL")


def _get_workflow_model() -> str | None:
    return os.getenv("EXTRACT_INFO_ORDER_MODEL") or _get_intent_model()


def _get_response_model() -> str | None:
    return os.getenv("CHATBOT_RESPONSE_MODEL") or _get_workflow_model()


def _ensure_llm_ready(model_name: str | None) -> None:
    if not model_name:
        raise RuntimeError("Model name is missing in environment configuration.")


def _parse_json_object(raw_text: str) -> Dict[str, Any]:
    raw = (raw_text or "").strip()
    if not raw:
        raise ValueError("LLM returned empty response.")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    if "```" in raw:
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        candidate = raw[start : end + 1]
        return json.loads(candidate)

    raise ValueError("LLM response is not valid JSON object.")


def _parse_json_payload(raw_text: str) -> Any:
    raw = (raw_text or "").strip()
    if not raw:
        raise ValueError("LLM returned empty response.")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    if "```" in raw:
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    obj_start = raw.find("{")
    obj_end = raw.rfind("}")
    if obj_start >= 0 and obj_end > obj_start:
        candidate = raw[obj_start : obj_end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    arr_start = raw.find("[")
    arr_end = raw.rfind("]")
    if arr_start >= 0 and arr_end > arr_start:
        candidate = raw[arr_start : arr_end + 1]
        return json.loads(candidate)

    raise ValueError("LLM response is not valid JSON payload.")


def _safe_json_dumps(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return str(data)


def _message_content_for_log(content: Any) -> str:
    if isinstance(content, str):
        return content
    return _safe_json_dumps(content)


def _dump_openai_response(response: Any) -> str:
    if hasattr(response, "model_dump_json"):
        try:
            return response.model_dump_json()
        except Exception:
            pass
    if hasattr(response, "model_dump"):
        try:
            return _safe_json_dumps(response.model_dump())
        except Exception:
            pass
    return str(response)


def _chat_completion_with_full_logging(
    *,
    step_name: str,
    model_name: str,
    messages: List[Dict[str, Any]],
) -> tuple[Any, str]:
    client = _get_openai_client()
    logger.info(
        "AI_CALL_REQUEST_META step=%s model=%s message_count=%s",
        step_name,
        model_name,
        len(messages),
    )

    for index, msg in enumerate(messages):
        role = str(msg.get("role", ""))
        content = _message_content_for_log(msg.get("content"))
        logger.info(
            "AI_CALL_REQUEST_MESSAGE step=%s index=%s role=%s content=\n%s",
            step_name,
            index,
            role,
            content,
        )

    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
    )

    logger.info(
        "AI_CALL_RESPONSE step=%s response=%s",
        step_name,
        _dump_openai_response(response),
    )

    raw = (response.choices[0].message.content or "").strip()
    logger.info(
        "AI_CALL_RESPONSE_CONTENT step=%s content=%s",
        step_name,
        raw,
    )
    return response, raw


def _normalize_intent(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized in ALLOWED_INTENTS:
        return normalized
    return "other"


async def detect_intent(
    text: str,
    history: list[str] | None = None,
    asked_slots: list[str] | None = None,
    missing_slots: list[str] | None = None,
) -> Tuple[str, float, str]:
    model_name = _get_intent_model()
    _ensure_llm_ready(model_name)
    intent_payload = {
        "current_message": text,
        "history_last_5": history or [],
        "asked_slots": asked_slots or [],
        "missing_slots": missing_slots or [],
    }

    try:
        _response, raw = _chat_completion_with_full_logging(
            step_name="detect_intent",
            model_name=model_name,
            messages=[
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(intent_payload, ensure_ascii=False)},
            ],
        )
        data = _parse_json_object(raw)
        intent = _normalize_intent(str(data.get("intent", "")))

        confidence = data.get("confidence", 0.5)
        if isinstance(confidence, str):
            confidence = float(confidence)
        if not isinstance(confidence, (int, float)):
            confidence = 0.5
        confidence = max(0.0, min(1.0, float(confidence)))
        logger.info(
            "AI_STEP=detect_intent model=%s parsed_intent=%s confidence=%.4f history_count=%s raw=%s",
            model_name,
            intent,
            confidence,
            len(intent_payload["history_last_5"]),
            raw,
        )
        return intent, confidence, raw
    except Exception as exc:
        logger.exception("detect_intent failed: %s", exc)
        raise RuntimeError("Intent detection failed from LLM") from exc


def _normalize_branch_from_options(branch_value: Any, branch_options: List[Dict[str, str]]) -> str | None:
    raw = str(branch_value or "").strip().lower()
    if not raw:
        return None
    normalized_map = {
        str(item.get("name") or "").strip().lower(): str(item.get("name") or "").strip()
        for item in branch_options
        if str(item.get("name") or "").strip()
    }
    return normalized_map.get(raw)


async def _load_branch_options() -> List[Dict[str, str]]:
    branches = await Branch.find_all().to_list()
    options: List[Dict[str, str]] = []
    for item in branches:
        name = str(item.name or "").strip()
        if not name:
            continue
        options.append(
            {
                "name": name,
                "label": str(item.label or "").strip() if item.label else "",
            }
        )
    return options


async def _load_slot_options(branch_name: str | None) -> List[Dict[str, str]]:
    slot_docs = await SlotCatalog.find_all().to_list()
    options: List[Dict[str, str]] = []
    normalized_branch = str(branch_name or "").strip()

    for item in slot_docs:
        slot_name = str(item.name or "").strip()
        if not slot_name:
            continue

        applies_to = [str(value or "").strip() for value in (item.applies_to or []) if str(value or "").strip()]
        if normalized_branch:
            if applies_to and "all" not in applies_to and normalized_branch not in applies_to:
                continue

        options.append(
            {
                "name": slot_name,
                "label": str(item.label or "").strip() if item.label else "",
                "description": str(item.description or "").strip(),
            }
        )

    return options


async def detect_branch(
    text: str,
    intent: str | None = None,
    branch_hint: str | None = None,
) -> Tuple[str | None, float, str]:
    model_name = _get_workflow_model()
    _ensure_llm_ready(model_name)
    branch_options = await _load_branch_options()

    if not branch_options:
        raise RuntimeError("No branch options found in database.")

    user_payload = {
        "intent": intent,
        "branch_hint": branch_hint,
        "text": text,
        "branch_options": branch_options,
    }

    try:
        _response, raw = _chat_completion_with_full_logging(
            step_name="detect_branch",
            model_name=model_name,
            messages=[
                {"role": "system", "content": BRANCH_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        )
        data = _parse_json_object(raw)

        branch = _normalize_branch_from_options(data.get("branch"), branch_options)

        confidence = data.get("confidence", 0.5)
        if isinstance(confidence, str):
            confidence = float(confidence)
        if not isinstance(confidence, (int, float)):
            confidence = 0.5
        confidence = max(0.0, min(1.0, float(confidence)))
        logger.info(
            "AI_STEP=detect_branch model=%s parsed_branch=%s confidence=%.4f raw=%s",
            model_name,
            branch,
            confidence,
            raw,
        )
        return branch, confidence, raw
    except Exception as exc:
        logger.exception("detect_branch failed: %s", exc)
        raise RuntimeError("Branch detection failed from LLM") from exc


async def detect_slots(
    text: str,
    intent: str | None = None,
    branch_name: str | None = None,
) -> Tuple[List[Dict[str, Any]], float, str]:
    model_name = _get_workflow_model()
    _ensure_llm_ready(model_name)
    slot_options = await _load_slot_options(branch_name)

    if not slot_options:
        logger.info("AI_STEP=detect_slots no_slot_options_for_branch=%s", branch_name)
        return None, None, 0.0, ""

    user_payload = {
        "intent": intent,
        "branch_name": branch_name,
        "text": text,
        "slot_options": slot_options,
    }

    try:
        _response, raw = _chat_completion_with_full_logging(
            step_name="detect_slots",
            model_name=model_name,
            messages=[
                {"role": "system", "content": SLOT_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        )
        data = _parse_json_payload(raw)

        allowed_slot_names = {
            str(item.get("name") or "").strip()
            for item in slot_options
            if str(item.get("name") or "").strip()
        }

        if isinstance(data, dict):
            items = [data]
        elif isinstance(data, list):
            items = data
        else:
            raise ValueError("LLM response is not a JSON object or array.")

        slot_items: List[Dict[str, Any]] = []
        max_confidence = 0.0
        for item in items:
            if not isinstance(item, dict):
                continue
            slot_candidate = str(item.get("slot") or "").strip()
            if slot_candidate not in allowed_slot_names:
                continue
            conf_value = item.get("confidence", 0.5)
            if isinstance(conf_value, str):
                conf_value = float(conf_value)
            if not isinstance(conf_value, (int, float)):
                conf_value = 0.5
            conf_value = max(0.0, min(1.0, float(conf_value)))
            max_confidence = max(max_confidence, conf_value)
            slot_items.append(
                {
                    "slot": slot_candidate,
                    "value": item.get("value"),
                    "confidence": conf_value,
                }
            )

        logger.info(
            "AI_STEP=detect_slots model=%s branch=%s slots=%s max_confidence=%.4f raw=%s",
            model_name,
            branch_name,
            _safe_json_dumps(slot_items),
            max_confidence,
            raw,
        )
        return slot_items, max_confidence, raw
    except Exception as exc:
        logger.exception("detect_slots failed: %s", exc)
        raise RuntimeError("Slot detection failed from LLM") from exc


async def decide_next_action(
    intent: str,
    branch: str | None,
    slots: Dict[str, Any],
    asked_slots: Optional[List[str]] = None,
    missing_slots: Optional[List[str]] = None,
    history_last_5: Optional[List[str]] = None,
) -> tuple[str, str | None, str, str]:
    allowed_actions = ["ask_slot", "call_rag", "recommend", "quote", "handoff"]
    model_name = _get_workflow_model()
    _ensure_llm_ready(model_name)
    system_prompt = """
You decide the next action in a wedding consultation workflow.
Return strictly valid JSON only:
{
  "next_action": "ask_slot|call_rag|recommend|quote|handoff",
  "next_slot": "slot_name_or_null",
  "reason": "short_reason"
}

Rules:
- Use `quote` when user asks price/package quote.
- Use `call_rag` for general service information lookup.
- Use `recommend` for recommendation/consultation continuation.
- Use `ask_slot` only when another slot is needed before proceeding.
- Use `handoff` if human support is needed.
- Use asked_slots, missing_slots, and history_last_5 as supportive context signals.
""".strip()

    user_payload = {
        "intent": intent,
        "branch": branch,
        "slots": slots,
        "asked_slots": asked_slots or [],
        "missing_slots": missing_slots or [],
        "history_last_5": history_last_5 or [],
        "allowed_actions": allowed_actions,
    }

    try:
        _response, raw = _chat_completion_with_full_logging(
            step_name="decide_next_action",
            model_name=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        )
        data = _parse_json_object(raw)

        next_action = str(data.get("next_action", "")).strip()
        if next_action not in allowed_actions:
            next_action = "handoff"

        next_slot = data.get("next_slot")
        if next_slot is not None:
            next_slot = str(next_slot).strip() or None

        reason = str(data.get("reason", "ai_decision")).strip() or "ai_decision"
        logger.info(
            "AI_STEP=decide_next_action model=%s parsed_next_action=%s next_slot=%s reason=%s raw=%s",
            model_name,
            next_action,
            next_slot,
            reason,
            raw,
        )
        return next_action, next_slot, reason, raw
    except Exception as exc:
        logger.exception("decide_next_action failed: %s", exc)
        raise RuntimeError("Decide next action failed from LLM") from exc


async def generate_slot_question(
    slot_name: str,
    branch: str | None,
    intent: str,
    known_slots: Dict[str, Any],
    asked_slot_values: Dict[str, Any],
    user_text: str,
    customer_name: str | None = None,
    recent_history: Optional[List[Dict[str, str]]] = None,
) -> tuple[str, str]:
    slot_def = get_slot_definition(slot_name) or {}
    slot_label = slot_def.get("label") or slot_name
    slot_description = slot_def.get("description") or ""
    evidence = slot_def.get("evidence", [])
    synonyms = slot_def.get("synonyms", [])
    examples = slot_def.get("examples", [])
    applies_to = slot_def.get("applies_to", [])
    slot_type = slot_def.get("slot_type")
    required = slot_def.get("required")
    priority = slot_def.get("priority")

    model_name = _get_response_model()
    _ensure_llm_ready(model_name)
    system_prompt = """
You are a Vietnamese wedding photography consultant assistant.
Write exactly one concise follow-up question to collect ONE missing slot.
Return strictly JSON only:
{
  "question": "..."
}

Constraints:
- Vietnamese only.
- Friendly consultant tone, natural like a real staff chat.
- Prefer warm opening such as "Dạ" when appropriate (Optional).
- If customer_name is available, naturally mention it in greeting (example: "Dạ, anh Mạnh...").
- Use history to formulate appropriate questions.
- Keep wording short, conversational, and easy to answer.
- Ask only for the target slot, do not ask multiple questions.

Style examples:
- "Dạ mình dự định tổ chức đám cưới ở địa điểm nào thế ạ?"
- "Dạ anh/chị đã chốt ngày cưới cụ thể chưa ạ?"
""".strip()

    user_payload = {
        "intent": intent,
        "branch": branch,
        "target_slot": slot_name,
        "slot_label": slot_label,
        "slot_description": slot_description,
        "slot_evidence": evidence,
        "slot_synonyms": synonyms,
        "slot_examples": examples,
        "slot_applies_to": applies_to,
        "slot_type": slot_type,
        "slot_required": required,
        "slot_priority": priority,
        "customer_name": customer_name,
        "known_slots": known_slots,
        "asked_slot_values": asked_slot_values,
        "latest_user_message": user_text,
        "recent_conversation_history": recent_history or [],
    }
    if intent == "other":
        user_payload = {
            "intent": intent,
            "latest_user_message": user_text,
            "recent_conversation_history": recent_history or [],
        }

    try:
        _response, raw = _chat_completion_with_full_logging(
            step_name="generate_slot_question",
            model_name=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        )
        data = _parse_json_object(raw)
        question = str(data.get("question", "")).strip()
        if not question:
            raise ValueError("LLM did not return question text.")
        logger.info(
            "AI_STEP=generate_slot_question model=%s slot=%s question=%s raw=%s",
            model_name,
            slot_name,
            question,
            raw,
        )
        return question, raw
    except Exception as exc:
        logger.exception("generate_slot_question failed: %s", exc)
        raise RuntimeError("Generate slot question failed from LLM") from exc


async def generate_action_response(
    action: str,
    intent: str,
    branch: str | None,
    slots: Dict[str, Any],
    latest_user_message: str,
) -> tuple[str, str]:
    model_name = _get_response_model()
    _ensure_llm_ready(model_name)
    system_prompt = """
You are a Vietnamese wedding consultation assistant.
Generate exactly one assistant reply for the provided action.
Return strictly JSON only:
{
  "message": "..."
}

Rules:
- Vietnamese only.
- Keep it concise, polite, and helpful.
- If action is `quote`, provide a brief quote-oriented response and ask for any needed clarification.
- If action is `call_rag`, provide concise service info guidance and ask one relevant follow-up.
- If action is `recommend`, provide a short recommendation and next step.
- If action is `handoff`, state that a human consultant will continue support.
""".strip()

    user_payload = {
        "action": action,
        "intent": intent,
        "branch": branch,
        "known_slots": slots,
        "latest_user_message": latest_user_message,
    }

    try:
        _response, raw = _chat_completion_with_full_logging(
            step_name="generate_action_response",
            model_name=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        )
        data = _parse_json_object(raw)
        message = str(data.get("message", "")).strip()
        if not message:
            raise ValueError("LLM did not return action response text.")

        logger.info(
            "AI_STEP=generate_action_response model=%s action=%s message=%s raw=%s",
            model_name,
            action,
            message,
            raw,
        )
        return message, raw
    except Exception as exc:
        logger.exception("generate_action_response failed: %s", exc)
        raise RuntimeError("Generate action response failed from LLM") from exc
