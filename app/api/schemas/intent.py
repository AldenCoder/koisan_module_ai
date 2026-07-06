from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class IntentAnalysisRequest(BaseModel):
    text: str = Field(...)
    conversation_id: Optional[str] = Field(
        None,
        description="Luot dau gui null de tao conversation moi. Luot sau gui lai conversation_id da duoc tra ve.",
    )
    channel: Optional[str] = Field(None)
    customer_name: Optional[str] = Field(None)
    customer_id: Optional[str] = Field(None)
    message_mid: Optional[str] = Field(None)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IntentAnalysisResponse(BaseModel):
    intent: str = Field(...)
    confidence: float = Field(..., ge=0.0, le=1.0)
    raw_response: str = Field(...)
    message_id: Optional[str] = Field(None)
    conversation_id: Optional[str] = Field(None)
