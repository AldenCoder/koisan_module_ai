from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.services.foreground_common import (
    extract_foreground_from_path,
    get_clip_crop_aware_runtime,
)


@dataclass(frozen=True)
class ExportForegroundsResult:
    exported: int
    skipped_existing: int
    missing: int
    output_dir: str


def read_metadata(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"product_id", "source_image_path"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"Metadata must contain: {', '.join(sorted(required))}")
        return list(reader)


def output_path(
    output_dir: Path,
    row_index: int,
    product_id: str,
    source_image_path: str,
) -> Path:
    source = Path(source_image_path)
    safe_stem = source.stem.replace("/", "_")
    return output_dir / product_id / f"{row_index:05d}_{safe_stem}.png"


def export_foregrounds_service(
    *,
    metadata_path: str | Path,
    output_dir: str | Path,
    rembg_model: Optional[str] = None,
    max_side: Optional[int] = None,
    limit: Optional[int] = None,
    force: bool = False,
) -> ExportForegroundsResult:
    rows = read_metadata(Path(metadata_path).expanduser().resolve())
    if limit:
        rows = rows[:limit]

    resolved_output_dir = Path(output_dir).expanduser().resolve()
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    runtime = get_clip_crop_aware_runtime(rembg_model=rembg_model)
    resolved_max_side = max_side or settings.clip_crop_aware_max_side

    exported = 0
    skipped = 0
    missing = 0
    for row_index, row in enumerate(rows):
        source_path = Path(row["source_image_path"]).expanduser()
        target = output_path(
            resolved_output_dir,
            row_index,
            row["product_id"],
            row["source_image_path"],
        )
        if target.exists() and not force:
            skipped += 1
            continue
        if not source_path.exists():
            missing += 1
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        foreground = extract_foreground_from_path(
            source_path,
            runtime=runtime,
            max_side=resolved_max_side,
        )
        foreground.save(target)
        exported += 1

    return ExportForegroundsResult(
        exported=exported,
        skipped_existing=skipped,
        missing=missing,
        output_dir=str(resolved_output_dir),
    )
