from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ConversationStatusSchema(str, Enum):
    NEW = "new"
    CONFIRMED = "confirmed"
    HANDOVER = "handover"
    APILIMIT = "apilimit"
    ORDER_PENDING = "order_pending"


class ConversationListStatusFilterSchema(str, Enum):
    NEW = "new"
    HANDOVER = "handover"
    APILIMIT = "apilimit"
    CONFIRMED = "confirmed"
    ORDER_PENDING = "order_pending"


class ConversationStateShape(BaseModel):
    branch_id: Optional[str] = Field(None)
    branch: Optional[str] = Field(None)
    intent: Optional[str] = Field(None)
    rag_anchor_text: Optional[str] = Field(None)
    slots: Dict[str, Any] = Field(default_factory=dict)
    missing_slots: List[str] = Field(default_factory=list)
    asked_slots: List[str] = Field(default_factory=list)
    next_action: Optional[str] = Field(None)
    prev_slot: Optional[str] = Field(None)
    next_slot: Optional[str] = Field(None)


class BaseDocumentResponse(BaseModel):
    id: str = Field(...)
    created_at: datetime = Field(...)
    updated_at: datetime = Field(...)


class ConversationInfoResponse(BaseDocumentResponse):
    channel: Optional[str] = Field(None)
    customer_name: Optional[str] = Field(None)
    customer_id: Optional[str] = Field(None)
    pancake_page_id: Optional[str] = Field(None)
    pancake_conversation_id: Optional[str] = Field(None)
    pancake_thread_type: Optional[str] = Field(None)
    pancake_info_url: Optional[str] = Field(None)
    order_note: Optional[str] = Field(None)
    is_active: bool = Field(...)
    status: ConversationStatusSchema = Field(...)
    summaries: Optional[List[str]] = Field(None)
    version: Optional[str] = Field(None)


class ConversationCreateRequest(BaseModel):
    channel: Optional[str] = Field(None, max_length=100)
    customer_name: Optional[str] = Field(None, max_length=100)
    customer_id: Optional[str] = Field(None, max_length=100)
    status: ConversationStatusSchema = Field(default=ConversationStatusSchema.NEW)
    summaries: Optional[List[str]] = Field(default=None)


class ConversationUpdateRequest(BaseModel):
    channel: Optional[str] = Field(None, max_length=100)
    customer_name: Optional[str] = Field(None, max_length=100)
    customer_id: Optional[str] = Field(None, max_length=100)
    status: Optional[ConversationStatusSchema] = Field(None)
    summaries: Optional[List[str]] = Field(None)
    is_active: Optional[bool] = Field(None)


class ConversationListItemResponse(ConversationInfoResponse):
    message_count: int = Field(default=0, ge=0)


class ConversationListResponse(BaseModel):
    items: List[ConversationListItemResponse] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)
    page: int = Field(default=1, ge=1)
    size: int = Field(default=10, ge=1)


class ConversationDeleteResponse(BaseModel):
    conversation_id: str = Field(...)
    deleted: bool = Field(...)
    soft_delete: bool = Field(default=True)


class MessageInfoResponse(BaseDocumentResponse):
    conversation_id: str = Field(...)
    role: Optional[str] = Field(None)
    content: str = Field(...)
    meta: Dict[str, Any] = Field(default_factory=dict)


class StateSlotInfoResponse(BaseDocumentResponse):
    conversation_state_id: str = Field(...)
    slot_catalog_name: Optional[str] = Field(None)
    slot_value: Optional[str] = Field(None)
    slot_value_json: Dict[str, Any] = Field(default_factory=dict)


class StateMissingSlotInfoResponse(BaseDocumentResponse):
    conversation_state_id: str = Field(...)
    slot_catalog_name: Optional[str] = Field(None)
    priority: Optional[str] = Field(None)
    sort_order: Optional[str] = Field(None)


class StateAskedSlotInfoResponse(BaseDocumentResponse):
    conversation_state_id: str = Field(...)
    slot_catalog_name: Optional[str] = Field(None)


class ConversationStateInfoResponse(BaseDocumentResponse):
    conversation_id: str = Field(...)
    message_id: Optional[str] = Field(None)
    branch_id: str = Field(...)
    branch: Optional[str] = Field(None)
    intent: Optional[str] = Field(None)
    rag_anchor_text: Optional[str] = Field(None)
    turn_index: Optional[str] = Field(None)
    next_action: Optional[str] = Field(None)
    prev_slot: Optional[str] = Field(None)
    next_slot: Optional[str] = Field(None)
    state_slots: List[StateSlotInfoResponse] = Field(default_factory=list)
    state_missing_slots: List[StateMissingSlotInfoResponse] = Field(default_factory=list)
    state_asked_slots: List[StateAskedSlotInfoResponse] = Field(default_factory=list)


class ConversationDetailResponse(BaseModel):
    conversation: ConversationInfoResponse = Field(...)
    messages: List[MessageInfoResponse] = Field(default_factory=list)
    conversation_states: List[ConversationStateInfoResponse] = Field(default_factory=list)
