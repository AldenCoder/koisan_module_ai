import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.api.dependencies.time import now_vn
from app.models.branch_slots import BranchSlot
from app.models.branches import Branch
from app.models.slot_catalog import SlotCatalog
from logs.logging_config import logger

_SCHEMA_CACHE: Dict[str, Any] | None = None
INIT_FILE_PATH = ".initdb"


def _schema_file_path() -> Path:
    return Path(__file__).resolve().parents[2] / "schema.txt"


def _initdb_flag_path() -> Path:
    return Path(__file__).resolve().parents[2] / INIT_FILE_PATH


def _normalize_applies_to(applies_to: Any) -> List[str]:
    if not isinstance(applies_to, list):
        return []
    result: List[str] = []
    for item in applies_to:
        value = str(item or "").strip()
        if value and value not in result:
            result.append(value)
    return result


def get_workflow_catalog() -> Dict[str, Any]:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is not None:
        return _SCHEMA_CACHE

    schema_path = _schema_file_path()
    if not schema_path.exists():
        logger.info("schema.txt not found; workflow catalog loading skipped.")
        _SCHEMA_CACHE = {"branches": [], "slots": []}
        return _SCHEMA_CACHE

    data = json.loads(schema_path.read_text(encoding="utf-8"))
    _SCHEMA_CACHE = data
    return data


def get_branch_names() -> List[str]:
    catalog = get_workflow_catalog()
    return [b["name"] for b in catalog.get("branches", []) if b.get("name")]


def get_branch_definition_map() -> Dict[str, Dict[str, Any]]:
    catalog = get_workflow_catalog()
    result: Dict[str, Dict[str, Any]] = {}
    for branch in catalog.get("branches", []):
        branch_name = branch.get("name")
        if branch_name:
            result[branch_name] = branch
    return result


def get_branch_definition(branch_name: str) -> Dict[str, Any] | None:
    return get_branch_definition_map().get(branch_name)


def get_slot_definitions() -> List[Dict[str, Any]]:
    catalog = get_workflow_catalog()
    return catalog.get("slots", [])


def get_slot_definition_map() -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for slot in get_slot_definitions():
        slot_name = slot.get("slot_name")
        if slot_name:
            result[slot_name] = slot
    return result


def get_slot_definition(slot_name: str) -> Dict[str, Any] | None:
    return get_slot_definition_map().get(slot_name)


async def ensure_branch_and_slots_for_name(branch_name: str) -> Branch:
    normalized_branch_name = (branch_name or "").strip()
    if not normalized_branch_name:
        raise ValueError("branch_name is required")

    now = now_vn()
    branch_definition = get_branch_definition(normalized_branch_name) or {}
    branch_label: Optional[str] = branch_definition.get("description")

    branch = await Branch.find_one(Branch.name == normalized_branch_name)
    if not branch:
        branch = Branch(
            name=normalized_branch_name,
            label=branch_label,
            created_at=now,
            updated_at=now,
        )
        await branch.insert()
    else:
        if branch_label and branch.label != branch_label:
            branch.label = branch_label
            branch.updated_at = now
            await branch.save()

    priority_order = {"high": 1, "medium": 2, "low": 3}
    for idx, slot_data in enumerate(get_slot_definitions(), start=1):
        slot_name = slot_data.get("slot_name")
        if not slot_name:
            continue

        applies_to = _normalize_applies_to(slot_data.get("applies_to", []))
        if applies_to and "all" not in applies_to and normalized_branch_name not in applies_to:
            continue

        sort_order = priority_order.get(str(slot_data.get("priority", "")).lower(), 9) * 1000 + idx
        required = bool(slot_data.get("required", False))

        branch_slot = await BranchSlot.find_one(
            {
                "branch_id": branch.id,
                "slot_catalog_name": slot_name,
            }
        )
        if not branch_slot:
            branch_slot = BranchSlot(
                branch_id=branch.id,
                slot_catalog_name=slot_name,
                required=required,
                sort_order=sort_order,
                created_at=now,
                updated_at=now,
            )
            await branch_slot.insert()
        else:
            branch_slot.required = required
            branch_slot.sort_order = sort_order
            branch_slot.updated_at = now
            await branch_slot.save()

    return branch


async def ensure_workflow_catalog_seeded() -> None:
    catalog = get_workflow_catalog()
    now = now_vn()
    branches = catalog.get("branches", [])
    slots = catalog.get("slots", [])

    branch_inserted = 0
    branch_existing = 0
    branch_updated = 0

    for branch_data in branches:
        branch_name = branch_data.get("name")
        if not branch_name:
            continue

        branch_label = branch_data.get("description")
        existing_branch = await Branch.find_one(Branch.name == branch_name)
        if not existing_branch:
            branch = Branch(
                name=branch_name,
                label=branch_label,
                created_at=now,
                updated_at=now,
            )
            await branch.insert()
            branch_inserted += 1
        else:
            changed = False
            if existing_branch.label != branch_label:
                existing_branch.label = branch_label
                changed = True
            if changed:
                existing_branch.updated_at = now
                await existing_branch.save()
                branch_updated += 1
            branch_existing += 1

    slot_inserted = 0
    slot_existing = 0
    slot_updated = 0

    for slot_data in slots:
        slot_name = slot_data.get("slot_name")
        if not slot_name:
            continue

        slot = await SlotCatalog.find_one(SlotCatalog.name == slot_name)
        synonyms = json.dumps(slot_data.get("synonyms", []), ensure_ascii=False)
        examples = json.dumps(slot_data.get("examples", []), ensure_ascii=False)
        evidence = json.dumps(slot_data.get("evidence", []), ensure_ascii=False)
        applies_to = _normalize_applies_to(slot_data.get("applies_to", []))
        required = bool(slot_data.get("required", False))

        if not slot:
            slot = SlotCatalog(
                name=slot_name,
                label=slot_data.get("label"),
                description=slot_data.get("description", ""),
                required=required,
                slot_type=slot_data.get("slot_type"),
                priority=slot_data.get("priority"),
                applies_to=applies_to,
                synonyms=synonyms,
                examples=examples,
                evidence=evidence,
                created_at=now,
                updated_at=now,
            )
            await slot.insert()
            slot_inserted += 1
        else:
            changed = False
            if slot.label != slot_data.get("label"):
                slot.label = slot_data.get("label")
                changed = True
            if slot.description != slot_data.get("description", ""):
                slot.description = slot_data.get("description", "")
                changed = True
            if slot.required != required:
                slot.required = required
                changed = True
            if slot.slot_type != slot_data.get("slot_type"):
                slot.slot_type = slot_data.get("slot_type")
                changed = True
            if slot.priority != slot_data.get("priority"):
                slot.priority = slot_data.get("priority")
                changed = True
            if slot.applies_to != applies_to:
                slot.applies_to = applies_to
                changed = True
            if slot.synonyms != synonyms:
                slot.synonyms = synonyms
                changed = True
            if slot.examples != examples:
                slot.examples = examples
                changed = True
            if slot.evidence != evidence:
                slot.evidence = evidence
                changed = True
            if changed:
                slot.updated_at = now
                await slot.save()
                slot_updated += 1
            slot_existing += 1

    flag_path = _initdb_flag_path()
    flag_path.write_text(
        (
            f"Synced from schema.txt at {now.isoformat()}\n"
            f"branches_inserted={branch_inserted}, branches_existing={branch_existing}, branches_updated={branch_updated}\n"
            f"slots_inserted={slot_inserted}, slots_existing={slot_existing}, slots_updated={slot_updated}\n"
        ),
        encoding="utf-8",
    )

    logger.info(
        "Schema synced from schema.txt (branches inserted=%s existing=%s updated=%s; slots inserted=%s existing=%s updated=%s)",
        branch_inserted,
        branch_existing,
        branch_updated,
        slot_inserted,
        slot_existing,
        slot_updated,
    )
