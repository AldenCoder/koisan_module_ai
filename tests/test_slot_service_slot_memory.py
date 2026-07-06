from app.services import slot_service as ss


def test_merge_slot_memory_fills_missing_values_for_allowed_slots():
    merged = ss._merge_slot_memory_into_extracted_slots(
        extracted_slots_map={"prewedding_shoot_type": None},
        slot_memory={"prewedding_shoot_type": "Studio"},
        allowed_slot_names={"prewedding_shoot_type", "desired_products_details"},
    )

    assert merged["prewedding_shoot_type"] == "Studio"


def test_merge_slot_memory_does_not_override_existing_extracted_value():
    merged = ss._merge_slot_memory_into_extracted_slots(
        extracted_slots_map={"prewedding_shoot_type": "Ngoài trời"},
        slot_memory={"prewedding_shoot_type": "Studio"},
        allowed_slot_names={"prewedding_shoot_type"},
    )

    assert merged["prewedding_shoot_type"] == "Ngoài trời"


def test_merge_slot_memory_skips_slots_outside_branch_scope():
    merged = ss._merge_slot_memory_into_extracted_slots(
        extracted_slots_map={},
        slot_memory={"prewedding_shoot_type": "Studio"},
        allowed_slot_names={"wedding_day_services_needed"},
    )

    assert "prewedding_shoot_type" not in merged

