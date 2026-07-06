from app.services.pancake_drive_image_color_service import (
    build_requested_color_match,
    detect_requested_color,
    extract_requested_color_phrases,
    name_matches_color_terms,
    parse_drive_file_color_from_name,
    parse_drive_folder_color_from_name,
)


def test_parse_drive_file_color_from_name_supports_single_word_color():
    assert parse_drive_file_color_from_name("vay_da_hoi_do.jpg") == "do"


def test_parse_drive_file_color_from_name_supports_joined_multi_word_color():
    assert parse_drive_file_color_from_name("vay_da_hoi_xanhngoc.jpg") == "xanhngoc"


def test_parse_drive_file_color_from_name_rejects_middle_color_token():
    assert parse_drive_file_color_from_name("vay_do_da_hoi.jpg") is None


def test_parse_drive_file_color_from_name_rejects_split_multi_word_color():
    assert parse_drive_file_color_from_name("vay_da_hoi_xanh_ngoc.jpg") is None


def test_parse_drive_file_color_from_name_rejects_filename_without_color_token():
    assert parse_drive_file_color_from_name("vay_da_hoi.jpg") is None


def test_parse_drive_folder_color_from_name_supports_plain_and_triggered_color():
    assert parse_drive_folder_color_from_name("đỏ") == "do"
    assert parse_drive_folder_color_from_name("màu đỏ") == "do"
    assert parse_drive_folder_color_from_name("Lookbook màu xanh ngọc") == "xanhngoc"


def test_detect_requested_color_requires_drive_link():
    assert detect_requested_color("Em gui chi anh mau do a", has_drive_link=False) is None


def test_detect_requested_color_supports_accented_trigger_and_color():
    assert detect_requested_color("Em gửi chị ảnh váy màu đỏ ạ", has_drive_link=True) == "do"
    assert detect_requested_color("Em gửi chị ảnh màu xanh ngọc ạ", has_drive_link=True) == "xanhngoc"


def test_detect_requested_color_rejects_unaccented_mau_trigger():
    assert detect_requested_color("Em gui chi anh mau do a", has_drive_link=True) is None


def test_detect_requested_color_does_not_match_color_without_trigger():
    assert detect_requested_color("Em gửi chị ảnh váy đỏ ạ", has_drive_link=True) is None


def test_detect_requested_color_does_not_treat_mau_as_mau_trigger():
    assert detect_requested_color("Em gửi chị mẫu đỏ này ạ", has_drive_link=True) is None


def test_detect_requested_color_does_not_match_color_list_after_colon():
    assert detect_requested_color(
        "Mẫu này có 4 màu: Xanh đá, Kem, Hồng, Tím ạ.",
        has_drive_link=True,
    ) is None


def test_extract_requested_color_phrases_splits_comma_list_after_accented_mau():
    phrases = extract_requested_color_phrases(
        "Mẫu có màu **Đỏ đô, Kem** ạ. Chị thích màu nào để em hỗ trợ tiếp nhé?",
        has_drive_link=True,
    )

    assert phrases == ["Đỏ đô", "Kem"]


def test_extract_requested_color_phrases_rejects_color_question_with_slash_text():
    result = build_requested_color_match(
        (
            "Dạ mẫu S2652146 giá 429.000đ ạ. "
            "Mẫu này có 3 màu: Be, Xanh biển, Tím.\n\n"
            "Ảnh lookbook: https://drive.google.com/drive/folders/root_folder\n\n"
            "Chị thích màu nào để em check size/còn hàng cho mình ạ?"
        ),
        has_drive_link=True,
    )

    assert result.primary is None
    assert result.phrases == []
    assert result.terms == []


def test_build_requested_color_match_supports_dynamic_multi_word_color_terms():
    result = build_requested_color_match(
        "Dạ em gửi chị ảnh lookbook mẫu W2651713 màu **Hồng sen** ạ.",
        has_drive_link=True,
    )

    assert result.primary == "hongsen"
    assert result.phrases == ["Hồng sen"]
    assert name_matches_color_terms("lookbook_hong_sen.jpg", result.terms)
    assert name_matches_color_terms("lookbook-hongsen.jpg", result.terms)
    assert name_matches_color_terms("folder hồng sen", result.terms)
    assert name_matches_color_terms("lookbook_hong.jpg", result.terms)
    assert name_matches_color_terms("lookbook_sen.jpg", result.terms)


def test_build_requested_color_match_keeps_existing_color_map_aliases():
    result = build_requested_color_match("Em gửi chị ảnh màu xanh ngọc ạ", has_drive_link=True)

    assert result.primary == "xanhngoc"
    assert name_matches_color_terms("lookbook_xanhngoc.jpg", result.terms)
