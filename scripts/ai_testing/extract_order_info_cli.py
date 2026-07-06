#!/usr/bin/env python3.11
"""CLI helper to test ai_service.extract_info_from_order() directly."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test app.services.ai_service.extract_info_from_order() without calling API routes.",
    )
    parser.add_argument(
        "text",
        nargs="?",
        help="User message to extract order information from.",
    )
    parser.add_argument(
        "--text-file",
        type=Path,
        help="Read the user message from a text file instead of positional text.",
    )
    parser.add_argument(
        "--intent",
        help="Optional intent hint passed to extract_info_from_order (e.g. update-order-item).",
    )
    parser.add_argument(
        "--message-history-file",
        type=Path,
        help='Path to JSON array of messages, e.g. [{"role":"user","content":"..."}, ...].',
    )
    parser.add_argument(
        "--order-items-file",
        type=Path,
        help='Path to JSON array of current order items, e.g. [{"product_name":"..."}, ...].',
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=ROOT / ".env",
        help="Optional .env file to load before running (default: ./\.env).",
    )
    parser.add_argument(
        "--raw-only",
        action="store_true",
        help="Print only the raw model response.",
    )
    args = parser.parse_args()

    if bool(args.text) == bool(args.text_file):
        parser.error("Provide exactly one of positional 'text' or --text-file.")

    return args


def load_json_file(path: Path, expected_type: type[list], label: str) -> list[dict[str, Any]]:
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(f"{label} file not found: {path}")
    except OSError as exc:
        raise SystemExit(f"Failed to read {label} file {path}: {exc}") from exc

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {label} file {path}: {exc}") from exc

    if not isinstance(data, expected_type):
        raise SystemExit(f"{label} file must contain a JSON {expected_type.__name__}.")

    return data


def load_text(args: argparse.Namespace) -> str:
    if args.text:
        return args.text

    try:
        return args.text_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise SystemExit(f"Text file not found: {args.text_file}")
    except OSError as exc:
        raise SystemExit(f"Failed to read text file {args.text_file}: {exc}") from exc


async def _run(args: argparse.Namespace) -> int:
    if args.env_file:
        load_dotenv(args.env_file)
    else:
        load_dotenv()

    missing_env = [
        name
        for name in ("OPENAI_API_KEY", "EXTRACT_INFO_ORDER_MODEL")
        if not os.getenv(name)
    ]
    if missing_env:
        print(
            "Missing required environment variables: " + ", ".join(missing_env),
            file=sys.stderr,
        )
        print(
            "Set them in your shell or .env before running this script.",
            file=sys.stderr,
        )
        return 2

    text = load_text(args)
    if not text:
        print("Input text is empty.", file=sys.stderr)
        return 2

    message_history = None
    if args.message_history_file:
        message_history = load_json_file(
            args.message_history_file,
            list,
            "message history",
        )

    order_items = None
    if args.order_items_file:
        order_items = load_json_file(
            args.order_items_file,
            list,
            "order items",
        )

    try:
        from app.services.ai_service import extract_info_from_order
    except Exception as exc:  # pragma: no cover - import-time env/client failures
        print(f"Failed to import ai_service.extract_info_from_order: {exc}", file=sys.stderr)
        return 3

    result = await extract_info_from_order(
        text=text,
        message_history=message_history,
        order_items=order_items,
        intent=args.intent,
    )
    if not result:
        print("extract_info_from_order returned no result (False).", file=sys.stderr)
        return 1

    if args.raw_only:
        print(result.raw_response)
        return 0

    if hasattr(result, "model_dump"):
        payload = result.model_dump(mode="json")
    else:
        payload = result.dict()

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    args = parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
