from pydantic import BaseModel, ConfigDict, Field


class OrderNoteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(..., min_length=1)
    order_note: str = Field(..., min_length=1, max_length=5000)


class OrderNoteCreateResponse(BaseModel):
    success: bool = Field(default=True)
    conversation_id: str = Field(...)
    status: str = Field(...)
    order_note: str = Field(...)
    order_note_index: int = Field(..., ge=1)
