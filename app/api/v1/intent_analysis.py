from fastapi import APIRouter, HTTPException

from app.api.schemas.branch import (
    BranchAnalysisRequest,
    BranchAnalysisResponse,
)
from app.api.schemas.slot import (
    SlotExtractionRequest,
    SlotExtractionResponse,
    SlotStateUpdateRequest,
    SlotStateUpdateResponse,
)
from app.api.schemas.intent import (
    IntentAnalysisRequest,
    IntentAnalysisResponse,
)
from app.services.conversation_service import (
    create_conversation_service,
    extract_intent_service,
    get_conversation_by_id_service,
    get_latest_conversation_by_customer_id_service,
    get_latest_conversation_by_customer_name_service,
    update_conversation_profile_service,
)
from app.services.branch_service import (
    extract_branch_service,
)
from app.services.slot_service import (
    extract_slots_service,
    prepare_update_slot_state_service,
    persist_update_slot_state_service,
)
from logs.logging_config import logger

router = APIRouter()

@router.post("/extract-intent", response_model=IntentAnalysisResponse)
async def extract_intent(payload: IntentAnalysisRequest) -> IntentAnalysisResponse:
    try:
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

        result = await extract_intent_service(
            text=payload.text,
            conversation=conversation,
            message_mid=payload.message_mid,
            metadata=payload.metadata,
        )

        return IntentAnalysisResponse(
            intent=result["intent"],
            confidence=float(result["confidence"]),
            raw_response=str(result["raw_response"]),
            message_id=result["message_id"],
            conversation_id=result["conversation_id"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Error in /extract-intent: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to extract intent") from exc


@router.post("/extract-branch", response_model=BranchAnalysisResponse)
async def extract_branch(payload: BranchAnalysisRequest) -> BranchAnalysisResponse:
    try:
        result = await extract_branch_service(
            text=payload.text,
            intent=payload.intent,
            branch_hint=payload.branch_hint,
        )
        return BranchAnalysisResponse(**result)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Error in /extract-branch: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to analyze branch") from exc


@router.post("/extract-slots", response_model=SlotExtractionResponse)
async def extract_slots(payload: SlotExtractionRequest) -> SlotExtractionResponse:
    try:
        result = await extract_slots_service(
            text=payload.text,
            intent=payload.intent,
            branch_hint=payload.branch_hint,
        )
        return SlotExtractionResponse(**result)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Error in /extract-slots: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to extract slots") from exc


@router.post("/update-slot-state", response_model=SlotStateUpdateResponse)
async def update_slot_state(payload: SlotStateUpdateRequest) -> SlotStateUpdateResponse:
    try:
        context = await prepare_update_slot_state_service(
            text=payload.text,
            intent=payload.intent,
            message_id=payload.message_id,
            conversation_id=payload.conversation_id,
            branch_name=payload.branch_name,
            slots=payload.slots,
            metadata=payload.metadata,
            raw_response=payload.raw_response,
        )
        result = await persist_update_slot_state_service(context)
        return SlotStateUpdateResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Error in /update-slot-state: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update slot state") from exc