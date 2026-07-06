from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.schemas.dataset_cleaning import DatasetCleaningResponse
from app.services.dataset_cleaning_service import clean_training_pairs_jsonl
from logs.logging_config import logger

router = APIRouter()


@router.post("/clean-training-pairs", response_model=DatasetCleaningResponse)
async def clean_training_pairs(file: UploadFile = File(...)) -> DatasetCleaningResponse:
    filename = file.filename or "uploaded.jsonl"
    if not filename.lower().endswith(".jsonl"):
        raise HTTPException(status_code=400, detail="Only .jsonl files are supported")

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        result = clean_training_pairs_jsonl(
            source_name=filename,
            content_bytes=content,
        )
        logger.info("DATASET_CLEANING_COMPLETED filename=%s result=%s", filename, result)
        return DatasetCleaningResponse(**result)
    except HTTPException:
        raise
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded JSONL") from exc
    except Exception as exc:
        logger.exception("Error in /dataset/clean-training-pairs: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to clean training pairs file") from exc
