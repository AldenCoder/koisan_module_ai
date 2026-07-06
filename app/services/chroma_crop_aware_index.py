from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Iterable, Optional

from fastapi import UploadFile
from PIL import Image
from starlette.concurrency import run_in_threadpool

from app.api.dependencies.error_codes import ErrorCode
from app.api.schemas.image_search import CropAwareImageSearchResponse
from app.core.config import settings
from app.services.crop_aware_index_common import (
    aggregate_image_matches,
    embed_crop_aware_images as _embed_crop_aware_images,
    prepare_crop_aware_index_rows as _prepare_crop_aware_index_rows,
)
from app.services.crop_views import DEFAULT_VIEWS, crop_alpha_view
from app.services.export_foregrounds import read_metadata
from app.services.foreground_common import (
    CropAwareImageSearchError,
    embed_prepared_images,
    extract_foreground_from_content,
    get_clip_crop_aware_runtime,
    parse_color,
    prepare_rgba_for_clip,
    read_image_search_upload,
)
_COLLECTION_CACHE: dict[tuple[str, str], object] = {}
_COLLECTION_CACHE_LOCK = Lock()


@dataclass(frozen=True)
class ChromaCropAwareIndexUpdate:
    output: str
    source_count: int
    added_view_count: int
    total_view_count: int
    created_index: bool
    foreground_cache_hits: int
    foreground_cache_misses: int


@dataclass(frozen=True)
class ChromaCropAwareDeleteUpdate:
    output: str
    source_count: int
    deleted_view_count: int
    total_view_count: int


def _load_chromadb():
    try:
        import chromadb
    except ImportError as exc:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_DEPENDENCY_MISSING,
            503,
        ) from exc
    return chromadb


def _persist_dir(persist_dir: Optional[str | Path] = None) -> Path:
    return Path(persist_dir or settings.chroma_persist_dir).expanduser().resolve()


def _collection_name(collection_name: Optional[str] = None) -> str:
    return collection_name or settings.chroma_image_search_collection


def _get_collection(
    *,
    persist_dir: Optional[str | Path] = None,
    collection_name: Optional[str] = None,
):
    resolved_dir = _persist_dir(persist_dir)
    resolved_name = _collection_name(collection_name)
    cache_key = (str(resolved_dir), resolved_name)

    with _COLLECTION_CACHE_LOCK:
        cached = _COLLECTION_CACHE.get(cache_key)
        if cached is not None:
            return cached

        try:
            resolved_dir.mkdir(parents=True, exist_ok=True)
            client = _load_chromadb().PersistentClient(path=str(resolved_dir))
            collection = client.get_or_create_collection(
                name=resolved_name,
                embedding_function=None,
                metadata={"hnsw:space": "cosine"},
            )
        except CropAwareImageSearchError:
            raise
        except Exception as exc:
            raise CropAwareImageSearchError(
                ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
                500,
            ) from exc

        _COLLECTION_CACHE[cache_key] = collection
        return collection


def clear_chroma_collection_cache() -> None:
    with _COLLECTION_CACHE_LOCK:
        _COLLECTION_CACHE.clear()


def _record_id(source_image_path: str, view_name: str) -> str:
    value = f"{Path(source_image_path).as_posix()}|{view_name}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _index_location(
    *,
    persist_dir: Optional[str | Path] = None,
    collection_name: Optional[str] = None,
) -> str:
    return f"{_persist_dir(persist_dir)}#{_collection_name(collection_name)}"


def upsert_sources_to_chroma_index_service(
    *,
    rows: Iterable[dict[str, str]],
    persist_dir: Optional[str | Path] = None,
    collection_name: Optional[str] = None,
    foreground_dir: Optional[str | Path] = None,
    clip_model: Optional[str] = None,
    rembg_model: Optional[str] = None,
    background: Optional[str] = None,
    max_side: Optional[int] = None,
    batch_size: int = 16,
    cache_foregrounds: bool = False,
) -> ChromaCropAwareIndexUpdate:
    source_rows = list(rows)
    if not source_rows:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            422,
        )

    resolved_foreground_dir = Path(
        foreground_dir or settings.clip_crop_aware_foreground_dir
    ).expanduser().resolve()
    runtime = get_clip_crop_aware_runtime(
        clip_model=clip_model,
        rembg_model=rembg_model,
    )
    try:
        (
            prepared_images,
            product_ids,
            source_image_paths,
            view_names,
            foreground_cache_hits,
            foreground_cache_misses,
        ) = _prepare_crop_aware_index_rows(
            source_rows,
            foreground_dir=resolved_foreground_dir,
            runtime=runtime,
            background=parse_color(background or settings.clip_crop_aware_background),
            max_side=max_side or settings.clip_crop_aware_max_side,
            cache_foregrounds=cache_foregrounds,
        )
        embeddings = _embed_crop_aware_images(
            prepared_images,
            runtime=runtime,
            batch_size=batch_size,
        )
        collection = _get_collection(
            persist_dir=persist_dir,
            collection_name=collection_name,
        )
        previous_count = collection.count()
        ids = [
            _record_id(source_image_path, view_name)
            for source_image_path, view_name in zip(source_image_paths, view_names)
        ]
        metadatas = [
            {
                "product_id": product_id,
                "source_image_path": source_image_path,
                "file_name": Path(source_image_path).name,
                "view_name": view_name,
            }
            for product_id, source_image_path, view_name in zip(
                product_ids,
                source_image_paths,
                view_names,
            )
        ]
        collection.upsert(
            ids=ids,
            embeddings=embeddings.tolist(),
            metadatas=metadatas,
        )
        total_count = collection.count()
    except CropAwareImageSearchError:
        raise
    except Exception as exc:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        ) from exc

    return ChromaCropAwareIndexUpdate(
        output=_index_location(
            persist_dir=persist_dir,
            collection_name=collection_name,
        ),
        source_count=len(source_rows),
        added_view_count=len(ids),
        total_view_count=total_count,
        created_index=previous_count == 0,
        foreground_cache_hits=foreground_cache_hits,
        foreground_cache_misses=foreground_cache_misses,
    )


def delete_sources_from_chroma_index_service(
    *,
    source_image_paths: Iterable[str],
    persist_dir: Optional[str | Path] = None,
    collection_name: Optional[str] = None,
) -> ChromaCropAwareDeleteUpdate:
    source_paths = list(dict.fromkeys(source_image_paths))
    collection = _get_collection(
        persist_dir=persist_dir,
        collection_name=collection_name,
    )
    ids = [
        _record_id(source_image_path, view.name)
        for source_image_path in source_paths
        for view in DEFAULT_VIEWS
    ]
    existing_count = 0
    if ids:
        try:
            existing = collection.get(ids=ids, include=[])
            existing_count = len(existing.get("ids") or [])
        except Exception:
            existing_count = len(ids)
        try:
            collection.delete(ids=ids)
        except Exception as exc:
            raise CropAwareImageSearchError(
                ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
                500,
            ) from exc

    return ChromaCropAwareDeleteUpdate(
        output=_index_location(
            persist_dir=persist_dir,
            collection_name=collection_name,
        ),
        source_count=len(source_paths),
        deleted_view_count=existing_count,
        total_view_count=collection.count(),
    )


def build_chroma_index_from_metadata_service(
    *,
    metadata_path: Optional[str | Path] = None,
    persist_dir: Optional[str | Path] = None,
    collection_name: Optional[str] = None,
    foreground_dir: Optional[str | Path] = None,
    batch_size: int = 16,
) -> ChromaCropAwareIndexUpdate:
    path = Path(
        metadata_path or settings.clip_crop_aware_metadata_path
    ).expanduser().resolve()
    try:
        rows = [
            {
                "product_id": row["product_id"],
                "source_image_path": row["source_image_path"],
            }
            for row in read_metadata(path)
            if Path(row["source_image_path"]).expanduser().is_file()
        ]
    except (OSError, ValueError) as exc:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        ) from exc

    return upsert_sources_to_chroma_index_service(
        rows=rows,
        persist_dir=persist_dir,
        collection_name=collection_name,
        foreground_dir=foreground_dir,
        batch_size=batch_size,
        cache_foregrounds=False,
    )


def _new_query_output_dir(output_dir: Optional[str | Path] = None) -> Path:
    root = Path(
        output_dir or settings.clip_crop_aware_output_dir
    ).expanduser().resolve()
    request_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    path = root / f"{request_id}_{secrets.token_hex(4)}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def search_chroma_crop_aware_image_bytes(
    *,
    content: bytes,
    filename: Optional[str] = None,
    persist_dir: Optional[str | Path] = None,
    collection_name: Optional[str] = None,
    output_dir: Optional[str | Path] = None,
    top_k: int = 10,
    aggregate_k: int = 1,
    clip_model: Optional[str] = None,
    rembg_model: Optional[str] = None,
    background: Optional[str] = None,
    max_side: Optional[int] = None,
    save_debug_images: bool = False,
) -> CropAwareImageSearchResponse:
    if top_k < 1:
        raise ValueError("top_k must be greater than 0")
    if aggregate_k < 1:
        raise ValueError("aggregate_k must be greater than 0")

    collection = _get_collection(
        persist_dir=persist_dir,
        collection_name=collection_name,
    )
    record_count = collection.count()
    if record_count < 1:
        raise CropAwareImageSearchError(ErrorCode.IMAGE_SEARCH_INDEX_NOT_FOUND, 404)

    runtime = get_clip_crop_aware_runtime(
        clip_model=clip_model,
        rembg_model=rembg_model,
    )
    foreground = extract_foreground_from_content(
        content,
        runtime=runtime,
        max_side=max_side or settings.clip_crop_aware_max_side,
    )
    resolved_background = parse_color(background or settings.clip_crop_aware_background)

    query_output_dir = _new_query_output_dir(output_dir) if save_debug_images else None
    query_foreground_path: Optional[Path] = None
    query_view_paths: dict[str, str] = {}
    if query_output_dir is not None:
        query_foreground_path = query_output_dir / "query_foreground.png"
        foreground.save(query_foreground_path)

    query_images: list[Image.Image] = []
    query_view_names: list[str] = []
    for view in DEFAULT_VIEWS:
        cropped = crop_alpha_view(foreground, view)
        if query_output_dir is not None:
            view_path = query_output_dir / f"query_{view.name}.png"
            cropped.save(view_path)
            query_view_paths[view.name] = str(view_path)
        query_images.append(
            prepare_rgba_for_clip(
                cropped,
                background=resolved_background,
                crop_alpha=True,
            )
        )
        query_view_names.append(view.name)

    try:
        query_embeddings = embed_prepared_images(query_images, runtime=runtime)
        candidate_count = min(
            record_count,
            max(50, top_k * max(aggregate_k, 2) * len(DEFAULT_VIEWS)),
        )
        results = collection.query(
            query_embeddings=query_embeddings.tolist(),
            n_results=candidate_count,
            include=["metadatas", "distances"],
        )
        ids_by_query = results.get("ids") or []
        metadatas_by_query = results.get("metadatas") or []
        distances_by_query = results.get("distances") or []
    except CropAwareImageSearchError:
        raise
    except Exception as exc:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        ) from exc

    best_by_record: dict[str, dict[str, object]] = {}
    for query_index, record_ids in enumerate(ids_by_query):
        query_view = query_view_names[query_index]
        metadatas = metadatas_by_query[query_index]
        distances = distances_by_query[query_index]
        for record_id, metadata, distance in zip(record_ids, metadatas, distances):
            if not metadata:
                continue
            match = {
                "product_id": str(metadata["product_id"]),
                "score": max(-1.0, min(1.0, 1.0 - float(distance))),
                "source_image_path": str(metadata["source_image_path"]),
                "index_view": str(metadata["view_name"]),
                "query_view": query_view,
            }
            previous = best_by_record.get(record_id)
            if previous is None or float(match["score"]) > float(previous["score"]):
                best_by_record[record_id] = match

    image_matches = sorted(
        best_by_record.values(),
        key=lambda item: float(item["score"]),
        reverse=True,
    )
    product_matches = aggregate_image_matches(image_matches, aggregate_k)
    return CropAwareImageSearchResponse(
        query=filename,
        query_foreground=(
            str(query_foreground_path) if query_foreground_path else None
        ),
        query_views=query_view_paths,
        index_path=_index_location(
            persist_dir=persist_dir,
            collection_name=collection_name,
        ),
        top_k=top_k,
        aggregate_k=aggregate_k,
        ranking=product_matches[:top_k],
        top_images=image_matches[:top_k],
    )


async def search_chroma_crop_aware_image_service(
    *,
    upload: UploadFile,
    top_k: int = 10,
    aggregate_k: int = 1,
) -> CropAwareImageSearchResponse:
    content = await read_image_search_upload(upload)
    return await run_in_threadpool(
        search_chroma_crop_aware_image_bytes,
        content=content,
        filename=upload.filename,
        top_k=top_k,
        aggregate_k=aggregate_k,
        save_debug_images=False,
    )
