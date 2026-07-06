from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from PIL import Image

from app.api.dependencies.error_codes import ErrorCode
from app.services.crop_views import DEFAULT_VIEWS, crop_alpha_view
from app.services.foreground_common import (
    CropAwareImageSearchError,
    embed_prepared_images,
    extract_foreground_from_path,
    prepare_rgba_for_clip,
)


def foreground_cache_path(
    output_dir: Path,
    row_index: int,
    product_id: str,
    source_image_path: str,
) -> Path:
    source = Path(source_image_path)
    safe_stem = source.stem.replace("/", "_")
    return output_dir / product_id / f"{row_index:05d}_{safe_stem}.png"


def aggregate_image_matches(
    matches: List[dict[str, object]],
    aggregate_k: int,
) -> List[dict[str, object]]:
    by_product: dict[str, list[dict[str, object]]] = {}
    for match in matches:
        by_product.setdefault(str(match["product_id"]), []).append(match)

    results: list[dict[str, object]] = []
    for product_id, product_matches in by_product.items():
        ranked = sorted(
            product_matches,
            key=lambda item: float(item["score"]),
            reverse=True,
        )
        top = ranked[: max(1, aggregate_k)]
        score = sum(float(item["score"]) for item in top) / len(top)
        results.append(
            {
                "product_id": product_id,
                "score": float(score),
                "best_score": float(ranked[0]["score"]),
                "best_image_path": str(ranked[0]["source_image_path"]),
                "best_index_view": str(ranked[0]["index_view"]),
                "best_query_view": str(ranked[0]["query_view"]),
                "top_image_scores": [float(item["score"]) for item in top],
            }
        )
    return sorted(
        results,
        key=lambda item: float(item["score"]),
        reverse=True,
    )


def prepare_crop_aware_index_rows(
    rows: Iterable[dict[str, str]],
    *,
    foreground_dir: str | Path,
    runtime,
    background: tuple[int, int, int],
    max_side: int,
    start_index: int = 0,
    cache_foregrounds: bool = True,
) -> tuple[list[Image.Image], list[str], list[str], list[str], int, int]:
    prepared_images: list[Image.Image] = []
    product_ids: list[str] = []
    source_image_paths: list[str] = []
    view_names: list[str] = []
    foreground_cache_hits = 0
    foreground_cache_misses = 0
    resolved_foreground_dir = Path(foreground_dir).expanduser().resolve()

    for offset, row in enumerate(rows):
        source_image_path = row["source_image_path"]
        source_path = Path(source_image_path).expanduser()
        if not source_path.exists():
            raise CropAwareImageSearchError(ErrorCode.IMAGE_SEARCH_INVALID_IMAGE, 422)

        cached_foreground = foreground_cache_path(
            resolved_foreground_dir,
            start_index + offset,
            row["product_id"],
            source_image_path,
        )
        if cache_foregrounds and cached_foreground.exists():
            foreground = Image.open(cached_foreground).convert("RGBA")
            foreground_cache_hits += 1
        else:
            foreground = extract_foreground_from_path(
                source_path,
                runtime=runtime,
                max_side=max_side,
            )
            if cache_foregrounds:
                cached_foreground.parent.mkdir(parents=True, exist_ok=True)
                foreground.save(cached_foreground)
            foreground_cache_misses += 1

        for view in DEFAULT_VIEWS:
            cropped = crop_alpha_view(foreground, view)
            prepared_images.append(
                prepare_rgba_for_clip(
                    cropped,
                    background=background,
                    crop_alpha=True,
                )
            )
            product_ids.append(row["product_id"])
            source_image_paths.append(source_image_path)
            view_names.append(view.name)

    return (
        prepared_images,
        product_ids,
        source_image_paths,
        view_names,
        foreground_cache_hits,
        foreground_cache_misses,
    )


def embed_crop_aware_images(
    prepared_images: list[Image.Image],
    *,
    runtime,
    batch_size: int,
):
    embeddings = []
    for start in range(0, len(prepared_images), batch_size):
        batch = prepared_images[start : start + batch_size]
        embeddings.append(embed_prepared_images(batch, runtime=runtime))
    if not embeddings:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            422,
        )
    return runtime.np.concatenate(embeddings, axis=0)
