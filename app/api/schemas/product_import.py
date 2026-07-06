from pydantic import BaseModel, Field


class ProductImportResponse(BaseModel):
    output_path: str
    imported_count: int = Field(default=0, ge=0)
    fields: list[str] = Field(default_factory=list)
