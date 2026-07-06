from app.services.facebook_handover_detection_service import (
    HANDOVER_DETECTED_REASON,
    detect_handover_reply,
    normalize_handover_text,
)


def test_normalize_handover_text_removes_vietnamese_marks_and_punctuation():
    assert (
        normalize_handover_text("  Dạ, em chuyển bộ phận phụ trách kiểm tra ạ!  ")
        == "da em chuyen bo phan phu trach kiem tra a"
    )


def test_detect_handover_reply_matches_accented_sale_phrase():
    result = detect_handover_reply("Dạ em chuyển sale hỗ trợ anh/chị chi tiết hơn ạ.")

    assert result == {
        "detected": True,
        "reason": HANDOVER_DETECTED_REASON,
        "matched_pattern": "em chuyen sale",
    }


def test_detect_handover_reply_matches_unaccented_phrase():
    result = detect_handover_reply("Da em chuyen bo phan phu trach xu ly tiep a")

    assert result["detected"] is True
    assert result["reason"] == HANDOVER_DETECTED_REASON
    assert result["matched_pattern"] == "chuyen bo phan phu trach"


def test_detect_handover_reply_matches_apology_phrase():
    result = detect_handover_reply("D\u1ea1, em xin l\u1ed7i ch\u1ecb \u0111\u1ec3 em ki\u1ec3m tra th\u00eam \u1ea1.")

    assert result == {
        "detected": True,
        "reason": HANDOVER_DETECTED_REASON,
        "matched_pattern": "da em xin loi",
    }


def test_detect_handover_reply_matches_required_phase_one_patterns():
    examples = [
        "Dạ em chuyển bộ phận phụ trách kiểm tra ạ.",
        "Dạ chuyển bộ phận phụ trách giúp em case này.",
        "Dạ em chuyển sale hỗ trợ mình ạ.",
        "Trường hợp này cần bộ phận phụ trách kiểm tra thêm ạ.",
        "Dạ em chuyển xử lý cho anh/chị ạ.",
    ]

    for example in examples:
        assert detect_handover_reply(example)["detected"] is True


def test_detect_handover_reply_matches_wait_and_check_phrase():
    examples = [
        "Ch\u1ecb ch\u1edd em 1 l\u00e1t em check cho m\u00ecnh \u1ea1",
        "Da anh cho em mot lat em kiem tra lai a",
        "Cho em xiu em check cho minh a",
    ]

    for example in examples:
        result = detect_handover_reply(example)

        assert result["detected"] is True
        assert result["reason"] == HANDOVER_DETECTED_REASON
        assert result["matched_pattern"] == "cho em 1 lat em check"


def test_detect_handover_reply_ignores_unrelated_text_and_empty_values():
    assert detect_handover_reply("Dạ em tư vấn size cho chị ạ.") == {
        "detected": False,
        "reason": None,
        "matched_pattern": None,
    }
    assert detect_handover_reply("")["detected"] is False
    assert detect_handover_reply(None)["detected"] is False
