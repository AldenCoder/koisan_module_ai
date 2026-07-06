import unicodedata

from unidecode import unidecode


def normalize(text: str) -> str:
    return unidecode(text.lower().strip()) if text else ""


def normalize_text(text: str) -> str:
    if not text:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    ).lower()