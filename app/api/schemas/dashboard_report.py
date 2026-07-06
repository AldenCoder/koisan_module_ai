from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class DashboardReportFiltersResponse(BaseModel):
    from_date: datetime = Field(...)
    to_date: datetime = Field(...)
    page_id: Optional[str] = Field(None)
    thread_type: Optional[str] = Field(None)
    role: Optional[str] = Field(None)
    include_inactive: bool = Field(default=False)
    alert_limit: int = Field(default=20, ge=1)


class DashboardReportSummaryResponse(BaseModel):
    total_messages: int = Field(default=0, ge=0)
    text_messages: int = Field(default=0, ge=0)
    image_messages: int = Field(default=0, ge=0)
    user_messages: int = Field(default=0, ge=0)
    staff_messages: int = Field(default=0, ge=0)
    bot_messages: int = Field(default=0, ge=0)
    total_conversations: int = Field(default=0, ge=0)
    new_conversations: int = Field(default=0, ge=0)
    confirmed_conversations: int = Field(default=0, ge=0)
    handover_conversations: int = Field(default=0, ge=0)
    apilimit_conversations: int = Field(default=0, ge=0)
    order_pending_conversations: int = Field(default=0, ge=0)
    needs_support_count: int = Field(default=0, ge=0)
    order_alert_count: int = Field(default=0, ge=0)


class DashboardMessagesByDayResponse(BaseModel):
    date: str = Field(...)
    total: int = Field(default=0, ge=0)
    text: int = Field(default=0, ge=0)
    image: int = Field(default=0, ge=0)
    user: int = Field(default=0, ge=0)
    staff: int = Field(default=0, ge=0)
    bot: int = Field(default=0, ge=0)


class DashboardConversationStatusResponse(BaseModel):
    status: str = Field(...)
    count: int = Field(default=0, ge=0)


class DashboardNeedsSupportAlertResponse(BaseModel):
    conversation_id: str = Field(...)
    customer_name: Optional[str] = Field(None)
    customer_id: Optional[str] = Field(None)
    status: str = Field(...)
    reason: str = Field(...)
    pancake_page_id: Optional[str] = Field(None)
    pancake_conversation_id: Optional[str] = Field(None)
    pancake_info_url: Optional[str] = Field(None)
    order_note: Optional[str] = Field(None)
    bot_paused_until: Optional[datetime] = Field(None)
    updated_at: Optional[datetime] = Field(None)
    message_count: int = Field(default=0, ge=0)


class DashboardOrderAlertResponse(BaseModel):
    conversation_id: str = Field(...)
    customer_name: Optional[str] = Field(None)
    customer_id: Optional[str] = Field(None)
    status: str = Field(...)
    pancake_page_id: Optional[str] = Field(None)
    pancake_conversation_id: Optional[str] = Field(None)
    pancake_info_url: Optional[str] = Field(None)
    order_note: Optional[str] = Field(None)
    updated_at: Optional[datetime] = Field(None)
    message_count: int = Field(default=0, ge=0)


class DashboardAlertsResponse(BaseModel):
    needs_support: List[DashboardNeedsSupportAlertResponse] = Field(default_factory=list)
    orders: List[DashboardOrderAlertResponse] = Field(default_factory=list)


class DashboardReportResponse(BaseModel):
    filters: DashboardReportFiltersResponse = Field(...)
    summary: DashboardReportSummaryResponse = Field(...)
    messages_by_day: List[DashboardMessagesByDayResponse] = Field(default_factory=list)
    conversation_status: List[DashboardConversationStatusResponse] = Field(default_factory=list)
    alerts: DashboardAlertsResponse = Field(...)


class DashboardReportPageIdItemResponse(BaseModel):
    page_id: str = Field(...)
    conversation_count: int = Field(default=0, ge=0)
    message_count: int = Field(default=0, ge=0)
    latest_activity_at: Optional[datetime] = Field(None)


class DashboardReportPageIdsResponse(BaseModel):
    items: List[DashboardReportPageIdItemResponse] = Field(default_factory=list)
