from datetime import datetime
from typing import List, Optional
from beanie import PydanticObjectId
from pydantic import BaseModel, Field
from app.api.schemas.tac_nhan import TacNhanResponse
from app.api.schemas.quyen_han import QuyenHanResponse

class TacNhanQuyenHanResponse(BaseModel):
    id: PydanticObjectId
    tac_nhan: TacNhanResponse
    quyen_han: QuyenHanResponse
    thoi_gian_tao: datetime

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True

class AssignListQuyenHanRequest(BaseModel):
    quyen_han_ids: List[PydanticObjectId]

class AssignListQuyenHanResponse(BaseModel):
    assigned_count: int
    total_requested: int
    message: str
    assigned_quyen_han: List[QuyenHanResponse]