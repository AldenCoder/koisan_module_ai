from typing import Optional

from pydantic import BaseModel, Field


class BranchAnalysisRequest(BaseModel):
    text: str = Field(...)
    intent: str = Field(...)
    branch_hint: Optional[str] = Field(None)


class BranchAnalysisResponse(BaseModel):
    branch_name: Optional[str] = Field(None)
    raw_response: str = Field(default="")
