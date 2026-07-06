#!/usr/bin/env python3
"""Generate test_report.txt from logs/system.log.

Output format:
=== CASE N | step_name ===
INPUT:
<request_payload>
OUTPUT:
<response_payload>
"""
from __future__ import annotations

import re
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "system.log"
OUT_PATH = Path(__file__).resolve().parents[2] / "logs" / "test_report.txt"

TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} ")
REQ_RE = re.compile(r"AI_CALL_REQUEST_MESSAGE step=(\w+) index=1 role=user content=")
RESP_RE = re.compile(r"AI_CALL_RESPONSE_CONTENT step=(\w+) content=")
RAG_REQ_RE = re.compile(r"STEP_04_CALL_RAG_REQUEST\b")
RAG_RESP_RE = re.compile(r"STEP_04_CALL_RAG_RESPONSE\b")
RAG_STEP_NAME = "step_04_call_rag"


def _collect_block(lines: list[str], start_idx: int, inline: str) -> tuple[str, int]:
    """Collect block content starting at start_idx, stopping before next timestamp line."""
    if inline:
        content_lines = [inline]
    else:
        content_lines = []
    idx = start_idx
    while idx < len(lines):
        line = lines[idx]
        if TIMESTAMP_RE.match(line):
            break
        content_lines.append(line.rstrip("\n"))
        idx += 1
    # Trim possible trailing empty lines
    content = "\n".join(content_lines).strip("\n")
    return content, idx


def generate_report(log_path: Path, out_path: Path) -> int:
    if not log_path.exists():
        raise FileNotFoundError(f"Log file not found: {log_path}")

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)

    pending: dict[str, list[dict]] = {}
    ordered_cases: list[dict] = []

    i = 0
    while i < len(lines):
        line = lines[i]

        rag_req_match = RAG_REQ_RE.search(line)
        if rag_req_match:
            inline = line.split("payload=", 1)[1].rstrip("\n") if "payload=" in line else ""
            content, next_idx = _collect_block(lines, i + 1, inline)
            entry = {"step": RAG_STEP_NAME, "request": content, "response": ""}
            pending.setdefault(RAG_STEP_NAME, []).append(entry)
            ordered_cases.append(entry)
            i = next_idx
            continue

        rag_resp_match = RAG_RESP_RE.search(line)
        if rag_resp_match:
            inline = line.split("response=", 1)[1].rstrip("\n") if "response=" in line else ""
            content, next_idx = _collect_block(lines, i + 1, inline)
            queue = pending.get(RAG_STEP_NAME, [])
            if queue:
                queue[0]["response"] = content
                queue.pop(0)
            i = next_idx
            continue

        req_match = REQ_RE.search(line)
        if req_match:
            step = req_match.group(1)
            inline = line.split("content=", 1)[1].rstrip("\n")
            content, next_idx = _collect_block(lines, i + 1, inline)
            entry = {"step": step, "request": content, "response": ""}
            pending.setdefault(step, []).append(entry)
            ordered_cases.append(entry)
            i = next_idx
            continue

        resp_match = RESP_RE.search(line)
        if resp_match:
            step = resp_match.group(1)
            inline = line.split("content=", 1)[1].rstrip("\n")
            content, next_idx = _collect_block(lines, i + 1, inline)
            queue = pending.get(step, [])
            if queue:
                queue[0]["response"] = content
                queue.pop(0)
            i = next_idx
            continue

        i += 1

    # Write report
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for idx, entry in enumerate(ordered_cases, 1):
            f.write(f"=== CASE {idx} | {entry['step']} ===\n")
            f.write("INPUT:\n")
            f.write((entry["request"] or "").strip() + "\n")
            f.write("OUTPUT:\n")
            f.write((entry["response"] or "").strip() + "\n\n")

    return len(ordered_cases)


if __name__ == "__main__":
    count = generate_report(LOG_PATH, OUT_PATH)
    print(f"Wrote {OUT_PATH} with {count} cases")
