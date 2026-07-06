from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import init_db
from app.services.catalog_service import ensure_workflow_catalog_seeded
from app.api.schemas.intent import IntentAnalysisRequest
from app.api.v1.workflow_message import workflow_total_response


@dataclass
class MessageInput:
    text: str
    channel: str
    customer_name: Optional[str]
    customer_id: Optional[str]
    message_mid: Optional[str]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full conversation flow with real MongoDB and OpenAI calls."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--text", help="Latest user message to process.")
    source_group.add_argument(
        "--data-file",
        default=None,
        help="JSONL file containing messages to batch test.",
    )
    parser.add_argument("--conversation-id", default=None, help="Existing conversation id.")
    parser.add_argument("--channel", default="manual_cli", help="Conversation channel label.")
    parser.add_argument("--customer-name", default=None, help="Customer display name.")
    parser.add_argument("--customer-id", default=None, help="Customer stable id.")
    parser.add_argument("--message-mid", default=None, help="External message id.")
    parser.add_argument(
        "--metadata-json",
        default="{}",
        help="Extra metadata as a JSON object string.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of samples to run when using --data-file.",
    )
    parser.add_argument(
        "--progress-file",
        default=str(Path(__file__).resolve().parent / "test_full_flow_cli.progress.txt"),
        help="File storing the next message index to resume from.",
    )
    parser.add_argument(
        "--report-dir",
        default=str(Path(__file__).resolve().parent / "reports"),
        help="Directory to write batch reports.",
    )
    parser.add_argument(
        "--start-index",
        type=int,
        default=None,
        help="Override the resume index (0-based) for batch runs.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-sample details during batch runs.",
    )
    return parser.parse_args()


def _load_metadata(raw_metadata: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(raw_metadata)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--metadata-json must be valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise SystemExit("--metadata-json must decode to a JSON object.")
    return parsed


def _dump(data: Any, pretty: bool) -> str:
    if pretty:
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)
    return json.dumps(data, ensure_ascii=False, default=str)


def _load_progress(path: Path) -> int:
    if not path.exists():
        return 0
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError as exc:
        raise SystemExit(f"Progress file {path} must contain an integer.") from exc


def _save_progress(path: Path, next_index: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{next_index}\n", encoding="utf-8")


def _count_messages(data_file: Path) -> int:
    total = 0
    with data_file.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise SystemExit(
                    f"Invalid JSON on line {line_number} in {data_file}: {exc}"
                ) from exc
            messages = payload.get("messages", [])
            if not isinstance(messages, list):
                raise SystemExit(
                    f"Line {line_number} in {data_file} must contain a 'messages' array."
                )
            total += len(messages)
    return total


def _iter_messages(
    data_file: Path,
    default_channel: str,
    default_customer_name: Optional[str],
    default_customer_id: Optional[str],
    default_message_mid: Optional[str],
) -> Iterable[Tuple[int, MessageInput]]:
    index = 0
    with data_file.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise SystemExit(
                    f"Invalid JSON on line {line_number} in {data_file}: {exc}"
                ) from exc
            messages = payload.get("messages", [])
            if not isinstance(messages, list):
                raise SystemExit(
                    f"Line {line_number} in {data_file} must contain a 'messages' array."
                )
            for message in messages:
                if not isinstance(message, dict):
                    raise SystemExit(
                        f"Line {line_number} in {data_file} contains a non-object message."
                    )
                text = message.get("text")
                if not text:
                    raise SystemExit(
                        f"Line {line_number} in {data_file} contains a message without 'text'."
                    )
                yield index, MessageInput(
                    text=text,
                    channel=message.get("channel") or default_channel,
                    customer_name=message.get("customer-name") or default_customer_name,
                    customer_id=message.get("customer-id") or default_customer_id,
                    message_mid=message.get("message-mid") or default_message_mid,
                )
                index += 1


async def _run_single(
    message: MessageInput,
    metadata: Dict[str, Any],
    conversation_id: Optional[str],
    pretty: bool,
    verbose: bool,
) -> Dict[str, Any]:
    payload = IntentAnalysisRequest(
        text=message.text,
        conversation_id=conversation_id,
        channel=message.channel,
        customer_name=message.customer_name,
        customer_id=message.customer_id,
        message_mid=message.message_mid,
        metadata=metadata,
    )
    response = await workflow_total_response(payload)

    if verbose:
        print("TOTAL_RESPONSE")
        print(_dump(response.model_dump(mode="json"), pretty))
        print()

    return {"total_response": response.model_dump(mode="json")}


async def _run() -> int:
    args = _parse_args()
    metadata = _load_metadata(args.metadata_json)

    await init_db()
    await ensure_workflow_catalog_seeded()

    if args.text:
        message = MessageInput(
            text=args.text,
            channel=args.channel,
            customer_name=args.customer_name,
            customer_id=args.customer_id,
            message_mid=args.message_mid,
        )
        result = await _run_single(
            message=message,
            metadata=metadata,
            conversation_id=args.conversation_id,
            pretty=args.pretty,
            verbose=True,
        )
        if not args.pretty:
            print(_dump(result, args.pretty))
        return 0

    data_file = Path(args.data_file).expanduser().resolve()
    if not data_file.exists():
        raise SystemExit(f"Data file not found: {data_file}")

    report_dir = Path(args.report_dir).expanduser().resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    progress_path = Path(args.progress_file).expanduser().resolve()

    total_messages = _count_messages(data_file)
    start_index = args.start_index if args.start_index is not None else _load_progress(progress_path)
    if start_index < 0:
        raise SystemExit("--start-index must be >= 0.")
    if start_index >= total_messages:
        print(f"Nothing to do: start index {start_index} >= total messages {total_messages}.")
        return 0

    batch_size = max(1, args.batch_size)
    end_index_exclusive = min(total_messages, start_index + batch_size)
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    processed = 0
    success = 0
    failures: List[Dict[str, Any]] = []
    interrupted = False

    try:
        for index, message in _iter_messages(
            data_file,
            default_channel=args.channel,
            default_customer_name=args.customer_name,
            default_customer_id=args.customer_id,
            default_message_mid=args.message_mid,
        ):
            if index < start_index:
                continue
            if index >= end_index_exclusive:
                break

            processed += 1
            try:
                await _run_single(
                    message=message,
                    metadata=metadata,
                    conversation_id=args.conversation_id,
                    pretty=args.pretty,
                    verbose=args.verbose,
                )
                success += 1
            except Exception as exc:  # noqa: BLE001
                failures.append(
                    {
                        "index": index,
                        "text": message.text,
                        "customer_id": message.customer_id,
                        "message_mid": message.message_mid,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            finally:
                _save_progress(progress_path, index + 1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        interrupted = True

    finished_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    report = {
        "data_file": str(data_file),
        "progress_file": str(progress_path),
        "started_at": started_at,
        "finished_at": finished_at,
        "start_index": start_index,
        "end_index_exclusive": end_index_exclusive,
        "total_messages": total_messages,
        "processed": processed,
        "success": success,
        "failed": len(failures),
        "failures": failures,
        "interrupted": interrupted,
    }

    report_name = f"report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    report_path = report_dir / report_name
    report_path.write_text(_dump(report, True), encoding="utf-8")

    print("BATCH_REPORT")
    print(_dump(report, True))
    print(f"\nReport saved to: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
