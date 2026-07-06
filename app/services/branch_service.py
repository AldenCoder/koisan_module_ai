from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.branches import Branch
from app.services.ai_service import detect_branch


def _normalize_branch_name(value: Optional[str], allowed_branch_names: List[str]) -> Optional[str]:
    if not value:
        return None
    allowed_branch_map = {name.strip().lower(): name for name in allowed_branch_names}
    normalized_key = value.strip().lower()
    if not normalized_key:
        return None
    return allowed_branch_map.get(normalized_key)


async def _get_allowed_branch_names() -> List[str]:
    rows = await Branch.find_all().to_list()
    result: List[str] = []
    for row in rows:
        value = (row.name or "").strip()
        if value and value not in result:
            result.append(value)
    return result


async def extract_branch_service(
    *,
    text: str,
    intent: Optional[str],
    branch_hint: Optional[str],
    slot_map: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    allowed_branch_names = await _get_allowed_branch_names()
    branch_candidate, _confidence, raw = await detect_branch(
        text=text,
        intent=intent,
        branch_hint=branch_hint,
    )

    resolved_branch_name = _normalize_branch_name(branch_hint, allowed_branch_names)
    if not resolved_branch_name:
        resolved_branch_name = _normalize_branch_name(branch_candidate, allowed_branch_names)
    if not resolved_branch_name and allowed_branch_names:
        resolved_branch_name = allowed_branch_names[0]

    return {
        "branch_name": resolved_branch_name,
        "raw_response": raw,
    }
