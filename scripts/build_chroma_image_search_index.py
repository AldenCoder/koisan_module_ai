from __future__ import annotations

import argparse

from app.services.chroma_crop_aware_index import (
    build_chroma_index_from_metadata_service,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the persistent Chroma image-search index from source metadata."
    )
    parser.add_argument("--metadata-path")
    parser.add_argument("--persist-dir")
    parser.add_argument("--collection-name")
    parser.add_argument("--batch-size", type=int, default=16)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = build_chroma_index_from_metadata_service(
        metadata_path=args.metadata_path,
        persist_dir=args.persist_dir,
        collection_name=args.collection_name,
        batch_size=args.batch_size,
    )
    print(
        "Chroma index ready: "
        f"sources={result.source_count}, "
        f"views={result.total_view_count}, "
        f"location={result.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
