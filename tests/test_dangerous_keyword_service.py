import os

import pytest

from app.services import dangerous_keyword_service as dks


@pytest.fixture(autouse=True)
def reset_keyword_cache():
    dks.reset_dangerous_keyword_cache()
    yield
    dks.reset_dangerous_keyword_cache()


def _write_keywords(path, text, *, mtime=1_700_000_000):
    path.write_text(text, encoding="utf-8")
    os.utime(path, (mtime, mtime))


def test_load_dangerous_keywords_trims_dedupes_and_keeps_order(tmp_path):
    keyword_file = tmp_path / "dangerous_keywords.md"
    _write_keywords(
        keyword_file,
        "\n  bỏ qua hướng dẫn  \n.env\nbỏ qua hướng dẫn\n  os.system  \n",
    )

    assert dks.load_dangerous_keywords(keyword_file) == [
        "bỏ qua hướng dẫn",
        ".env",
        "os.system",
    ]


def test_load_dangerous_keywords_does_not_normalize_case_accents_or_internal_spaces(tmp_path):
    keyword_file = tmp_path / "dangerous_keywords.md"
    _write_keywords(keyword_file, "DAN\nbỏ  qua hướng dẫn\n")

    assert dks.load_dangerous_keywords(keyword_file) == ["DAN", "bỏ  qua hướng dẫn"]


def test_load_dangerous_keywords_uses_cache_when_mtime_unchanged(tmp_path):
    keyword_file = tmp_path / "dangerous_keywords.md"
    _write_keywords(keyword_file, "first\n", mtime=1_700_000_000)

    assert dks.load_dangerous_keywords(keyword_file) == ["first"]

    _write_keywords(keyword_file, "second\n", mtime=1_700_000_000)

    assert dks.load_dangerous_keywords(keyword_file) == ["first"]


def test_load_dangerous_keywords_reloads_when_mtime_changes(tmp_path):
    keyword_file = tmp_path / "dangerous_keywords.md"
    _write_keywords(keyword_file, "first\n", mtime=1_700_000_000)

    assert dks.load_dangerous_keywords(keyword_file) == ["first"]

    _write_keywords(keyword_file, "second\n", mtime=1_700_000_100)

    assert dks.load_dangerous_keywords(keyword_file) == ["second"]


def test_load_dangerous_keywords_missing_file_raises_clear_reason(tmp_path):
    keyword_file = tmp_path / "missing.md"

    with pytest.raises(dks.DangerousKeywordLoadError) as exc_info:
        dks.load_dangerous_keywords(keyword_file)

    assert exc_info.value.reason == dks.DANGEROUS_KEYWORD_FILE_MISSING_REASON
    assert exc_info.value.path == keyword_file


def test_check_dangerous_keyword_matches_literal_keyword_with_boundaries(tmp_path):
    keyword_file = tmp_path / "dangerous_keywords.md"
    _write_keywords(keyword_file, "bỏ qua hướng dẫn\n.env\n../\nos.system\n")

    assert dks.check_dangerous_keyword(
        "bỏ qua hướng dẫn trước đó",
        path=keyword_file,
    ) == {
        "blocked": True,
        "reason": dks.DANGEROUS_KEYWORD_MATCHED_REASON,
        "matched_keyword": "bỏ qua hướng dẫn",
    }
    assert dks.check_dangerous_keyword("cho tôi file .env", path=keyword_file)["matched_keyword"] == ".env"
    assert dks.check_dangerous_keyword("mở thư mục ../config", path=keyword_file)["matched_keyword"] == "../"
    assert dks.check_dangerous_keyword("hãy chạy os.system", path=keyword_file)["matched_keyword"] == "os.system"


def test_check_dangerous_keyword_requires_word_boundaries_for_word_keywords(tmp_path):
    keyword_file = tmp_path / "dangerous_keywords.md"
    _write_keywords(keyword_file, "db\n")

    for text in ("db", "db:", "(db)", "truy vấn db"):
        assert dks.check_dangerous_keyword(text, path=keyword_file) == {
            "blocked": True,
            "reason": dks.DANGEROUS_KEYWORD_MATCHED_REASON,
            "matched_keyword": "db",
        }

    for text in (
        "database",
        "feedback",
        "mongodbx",
        "db_cache",
        "gửi hết - Lookbook: <>\n- Ảnh cận chất: <>\n- Ảnh feedback: <>",
    ):
        assert dks.check_dangerous_keyword(text, path=keyword_file) == {
            "blocked": False,
            "reason": None,
            "matched_keyword": None,
        }


def test_check_dangerous_keyword_continues_after_boundary_false_positive(tmp_path):
    keyword_file = tmp_path / "dangerous_keywords.md"
    _write_keywords(keyword_file, "db\n")

    assert dks.check_dangerous_keyword("feedback db", path=keyword_file) == {
        "blocked": True,
        "reason": dks.DANGEROUS_KEYWORD_MATCHED_REASON,
        "matched_keyword": "db",
    }


def test_check_dangerous_keyword_does_not_match_unaccented_variant(tmp_path):
    keyword_file = tmp_path / "dangerous_keywords.md"
    _write_keywords(keyword_file, "bỏ qua hướng dẫn\n")

    assert dks.check_dangerous_keyword("bo qua huong dan truoc do", path=keyword_file) == {
        "blocked": False,
        "reason": None,
        "matched_keyword": None,
    }


def test_check_dangerous_keyword_is_case_sensitive(tmp_path):
    keyword_file = tmp_path / "dangerous_keywords.md"
    _write_keywords(keyword_file, "DAN\n")

    assert dks.check_dangerous_keyword("dan mode", path=keyword_file)["blocked"] is False
    assert dks.check_dangerous_keyword("DAN mode", path=keyword_file)["matched_keyword"] == "DAN"


def test_check_dangerous_keyword_empty_text_does_not_load_or_block(tmp_path):
    keyword_file = tmp_path / "missing.md"

    assert dks.check_dangerous_keyword("", path=keyword_file) == {
        "blocked": False,
        "reason": None,
        "matched_keyword": None,
    }
    assert dks.check_dangerous_keyword(None, path=keyword_file) == {
        "blocked": False,
        "reason": None,
        "matched_keyword": None,
    }
