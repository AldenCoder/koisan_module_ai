from __future__ import annotations

import re
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse


PANCAKE_AUTO_CONSULT_SOURCE = "pancake_auto_consult"
PANCAKE_MESSAGE_AD_CARD = "ad_card"
PANCAKE_MESSAGE_PAGE_COMMENT_REPLY_NOTICE = "page_comment_reply_notice"
PANCAKE_PRODUCT_CODE_MISSING_REASON = "pancake_product_code_missing"
PANCAKE_AUTO_CONSULT_DEFAULT_PRODUCT_CODE_REGEX = r"(?<![A-Za-z0-9])(?:[A-Za-z]?\d{6,8})(?:(?:[A-Za-z0-9]{1,3})|(?:[^\S\r\n]*-[^\S\r\n]*[A-Za-z0-9]{1,3}))?(?![A-Za-z0-9])"
PANCAKE_COMMENT_REPLY_NOTICE_TEXT = "Bạn đang phản hồi bình luận"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean_string(value: Any) -> str:
    return str(value or "").strip()


def _first_non_empty_string(*values: Any) -> str | None:
    for value in values:
        normalized = _clean_string(value)
        if normalized:
            return normalized
    return None


def _raw_message(normalized: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = _as_mapping(normalized.get("raw"))
    data = _as_mapping(raw.get("data"))
    return _as_mapping(data.get("message"))


def _message_tags_from_normalized(normalized: Mapping[str, Any]) -> list[Any]:
    return _as_list(_raw_message(normalized).get("message_tags"))


def _iter_message_tag_links(message_tags: Any) -> list[str]:
    links: list[str] = []
    for tag in _as_list(message_tags):
        tag_data = _as_mapping(tag)
        for key in ("link", "url", "href"):
            link = _clean_string(tag_data.get(key))
            if link:
                links.append(link)
    return links


def _iter_attachment_post_attachments(attachment: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    candidates = _as_list(attachment.get("post_attachments"))
    if not candidates:
        nested = _as_mapping(attachment.get("payload"))
        candidates = _as_list(nested.get("post_attachments"))
    return [_as_mapping(candidate) for candidate in candidates if isinstance(candidate, Mapping)]


def _first_post_attachment_description(attachments: Any) -> str | None:
    for attachment in _as_list(attachments):
        attachment_data = _as_mapping(attachment)
        for post_attachment in _iter_attachment_post_attachments(attachment_data):
            description = _clean_string(post_attachment.get("description"))
            if description:
                return description
    return None


def _first_attachment_text(attachments: Any) -> str | None:
    for attachment in _as_list(attachments):
        attachment_data = _as_mapping(attachment)
        text = _first_non_empty_string(
            attachment_data.get("name"),
            attachment_data.get("description"),
            attachment_data.get("title"),
        )
        if text:
            return text
    return None


def _extract_messages_from_response_node(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, list):
        return [_as_mapping(item) for item in value if isinstance(item, Mapping)]
    if not isinstance(value, Mapping):
        return []

    for key in ("messages", "items", "data"):
        nested = value.get(key)
        if isinstance(nested, list):
            return [_as_mapping(item) for item in nested if isinstance(item, Mapping)]
        if isinstance(nested, Mapping):
            messages = _extract_messages_from_response_node(nested)
            if messages:
                return messages
    return []


def extract_messages_from_pancake_response(response_data: Any) -> list[Mapping[str, Any]]:
    return _extract_messages_from_response_node(response_data)


def is_pancake_ad_card_message(normalized: Mapping[str, Any]) -> bool:
    message_mid = _clean_string(normalized.get("message_mid"))
    return message_mid.startswith("ad-")


def extract_comment_id_from_message_tags(message_tags: Any) -> str | None:
    for link in _iter_message_tag_links(message_tags):
        parsed_url = urlparse(link)
        query = parse_qs(parsed_url.query)
        comment_ids = query.get("comment_id") or query.get("commentId")
        for comment_id in comment_ids or []:
            normalized = _clean_string(comment_id)
            if normalized:
                return normalized
    return None


def is_pancake_page_comment_reply_notice(normalized: Mapping[str, Any]) -> bool:
    page_id = _clean_string(normalized.get("page_id"))
    if not page_id:
        return False

    sender_id = _clean_string(normalized.get("sender_id"))
    platform_sender_id = _clean_string(normalized.get("platform_sender_id"))
    if sender_id != page_id and platform_sender_id != page_id:
        return False

    if _clean_string(normalized.get("message_from_admin_name")):
        return False
    if _clean_string(normalized.get("message_from_uid")):
        return False
    if _as_list(normalized.get("attachments")):
        return False

    raw_message = _raw_message(normalized)
    text_candidates = [
        normalized.get("text"),
        raw_message.get("message"),
        raw_message.get("original_message"),
    ]
    if not any(PANCAKE_COMMENT_REPLY_NOTICE_TEXT in _clean_string(text) for text in text_candidates):
        return False

    return extract_comment_id_from_message_tags(raw_message.get("message_tags")) is not None


def normalize_auto_consult_description(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def extract_product_codes(
    description: Any,
    *,
    regex_pattern: str = PANCAKE_AUTO_CONSULT_DEFAULT_PRODUCT_CODE_REGEX,
) -> list[str]:
    normalized_description = normalize_auto_consult_description(description)
    if not normalized_description:
        return []

    try:
        pattern = re.compile(regex_pattern)
    except re.error:
        pattern = re.compile(PANCAKE_AUTO_CONSULT_DEFAULT_PRODUCT_CODE_REGEX)

    product_codes: list[str] = []
    seen: set[str] = set()
    for match in pattern.finditer(normalized_description):
        code = _clean_string(match.group(0))
        if not code or code.isdigit() or code in seen:
            continue
        seen.add(code)
        product_codes.append(code)
    return product_codes


def build_auto_consult_prompt(product_codes: list[str]) -> dict[str, Any]:
    normalized_codes = [_clean_string(code) for code in product_codes if _clean_string(code)]
    if not normalized_codes:
        return {
            "ok": False,
            "reason": PANCAKE_PRODUCT_CODE_MISSING_REASON,
            "product_codes": [],
        }

    product_codes_csv = ", ".join(normalized_codes)
    return {
        "ok": True,
        "reason": None,
        "product_codes": normalized_codes,
        "product_code_count": len(normalized_codes),
        "product_codes_csv": product_codes_csv,
        "prompt": f"tư vấn mẫu {product_codes_csv} và gửi ảnh lookbook",
    }


def build_auto_consult_prompt_from_description(
    description: Any,
    *,
    regex_pattern: str = PANCAKE_AUTO_CONSULT_DEFAULT_PRODUCT_CODE_REGEX,
) -> dict[str, Any]:
    normalized_description = normalize_auto_consult_description(description)
    product_codes = extract_product_codes(normalized_description, regex_pattern=regex_pattern)
    result = build_auto_consult_prompt(product_codes)
    result["description_present"] = bool(normalized_description)
    result["description_length"] = len(normalized_description)
    return result


def extract_post_message_from_normalized(normalized: Mapping[str, Any]) -> str:
    raw = _as_mapping(normalized.get("raw"))
    data = _as_mapping(raw.get("data"))
    post = _as_mapping(data.get("post"))
    return normalize_auto_consult_description(post.get("message"))


def build_customer_comment_ai_message(
    normalized: Mapping[str, Any],
    *,
    regex_pattern: str = PANCAKE_AUTO_CONSULT_DEFAULT_PRODUCT_CODE_REGEX,
    initial_product_prompt: bool = True,
) -> dict[str, Any]:
    comment_text = _clean_string(normalized.get("text"))
    post_message = extract_post_message_from_normalized(normalized)
    product_codes = extract_product_codes(post_message, regex_pattern=regex_pattern)
    if not product_codes:
        return {
            "content": comment_text,
            "product_codes": [],
            "product_code_count": 0,
            "augmented": False,
            "initial_product_prompt": False,
            "follow_up": False,
            "post_message_present": bool(post_message),
        }

    product_codes_csv = ", ".join(product_codes)
    if not initial_product_prompt:
        return {
            "content": comment_text,
            "product_codes": product_codes,
            "product_code_count": len(product_codes),
            "augmented": False,
            "initial_product_prompt": False,
            "follow_up": True,
            "post_message_present": bool(post_message),
        }

    normalized_comment = comment_text.rstrip(" ,")
    prefix = f"{normalized_comment}, " if normalized_comment else ""
    return {
        "content": (
            f"{prefix}tư vấn mã sản phẩm {product_codes_csv}, "
            "và gửi ảnh lookbook"
        ),
        "product_codes": product_codes,
        "product_code_count": len(product_codes),
        "augmented": True,
        "initial_product_prompt": True,
        "follow_up": False,
        "post_message_present": bool(post_message),
    }


def _find_message_by_id(messages: list[Mapping[str, Any]], message_id: str) -> Mapping[str, Any] | None:
    normalized_message_id = _clean_string(message_id)
    if not normalized_message_id:
        return None
    for message in messages:
        if _clean_string(message.get("id")) == normalized_message_id:
            return message
    return None


def _is_ad_click_attachment(attachment: Mapping[str, Any]) -> bool:
    return _clean_string(attachment.get("type")).lower() == "ad_click"


def _extract_ad_id_from_attachment(attachment: Mapping[str, Any]) -> str | None:
    nested_ad = _as_mapping(attachment.get("ad"))
    payload = _as_mapping(attachment.get("payload"))
    return _first_non_empty_string(
        attachment.get("ad_id"),
        attachment.get("adid"),
        nested_ad.get("id"),
        payload.get("ad_id"),
    )


def _ad_click_matches(ad_click: Mapping[str, Any], ad_id: str) -> bool:
    if not ad_id:
        return False
    candidates = [
        ad_click.get("ad_id"),
        ad_click.get("adid"),
        _as_mapping(ad_click.get("ad")).get("id"),
    ]
    return any(_clean_string(candidate) == ad_id for candidate in candidates)


def _extract_post_id_from_ad_click(ad_click: Mapping[str, Any]) -> str | None:
    nested_post = _as_mapping(ad_click.get("post"))
    return _first_non_empty_string(
        ad_click.get("post_id"),
        ad_click.get("postid"),
        nested_post.get("id"),
    )


def _find_post_id_for_ad(response_data: Any, *, ad_id: str | None, attachment: Mapping[str, Any]) -> str | None:
    payload = _as_mapping(attachment.get("payload"))
    direct_post_id = _first_non_empty_string(
        attachment.get("post_id"),
        payload.get("post_id"),
    )
    if direct_post_id:
        return direct_post_id

    if not ad_id:
        return None

    response = _as_mapping(response_data)
    response_candidates = [response]
    nested_data = _as_mapping(response.get("data"))
    if nested_data:
        response_candidates.append(nested_data)

    for candidate_response in response_candidates:
        for ad_click in _as_list(candidate_response.get("ad_clicks")):
            ad_click_data = _as_mapping(ad_click)
            if _ad_click_matches(ad_click_data, ad_id):
                post_id = _extract_post_id_from_ad_click(ad_click_data)
                if post_id:
                    return post_id

        for customer in _as_list(candidate_response.get("customers")):
            for ad_click in _as_list(_as_mapping(customer).get("ad_clicks")):
                ad_click_data = _as_mapping(ad_click)
                if _ad_click_matches(ad_click_data, ad_id):
                    post_id = _extract_post_id_from_ad_click(ad_click_data)
                    if post_id:
                        return post_id
    return None


def extract_ad_card_source_detail(
    normalized: Mapping[str, Any],
    response_data: Any,
) -> dict[str, Any]:
    trigger_message_mid = _clean_string(normalized.get("message_mid"))
    messages = extract_messages_from_pancake_response(response_data)
    ad_message = _find_message_by_id(messages, trigger_message_mid)
    if ad_message is None:
        return {
            "ok": False,
            "reason": "pancake_ad_message_not_found",
            "trigger_type": PANCAKE_MESSAGE_AD_CARD,
            "trigger_message_mid": trigger_message_mid,
        }

    ad_click_attachment = None
    for attachment in _as_list(ad_message.get("attachments")):
        attachment_data = _as_mapping(attachment)
        if _is_ad_click_attachment(attachment_data):
            ad_click_attachment = attachment_data
            break

    if ad_click_attachment is None:
        return {
            "ok": False,
            "reason": "pancake_ad_click_missing",
            "trigger_type": PANCAKE_MESSAGE_AD_CARD,
            "trigger_message_mid": trigger_message_mid,
        }

    description = _first_post_attachment_description([ad_click_attachment])
    if not description:
        return {
            "ok": False,
            "reason": "pancake_ad_description_missing",
            "trigger_type": PANCAKE_MESSAGE_AD_CARD,
            "trigger_message_mid": trigger_message_mid,
        }

    ad_id = _extract_ad_id_from_attachment(ad_click_attachment)
    post_id = _find_post_id_for_ad(response_data, ad_id=ad_id, attachment=ad_click_attachment)
    return {
        "ok": True,
        "reason": None,
        "trigger_type": PANCAKE_MESSAGE_AD_CARD,
        "trigger_message_mid": trigger_message_mid,
        "ad_message_mid": trigger_message_mid,
        "description": description,
        "ad_id": ad_id,
        "post_id": post_id,
    }


def _message_contains_comment_id(message: Mapping[str, Any], comment_id: str) -> bool:
    if extract_comment_id_from_message_tags(message.get("message_tags")) == comment_id:
        return True

    for attachment in _as_list(message.get("attachments")):
        attachment_data = _as_mapping(attachment)
        comment = _as_mapping(attachment_data.get("comment"))
        metadata = _as_mapping(attachment_data.get("metadata"))
        for candidate in (
            comment.get("msg_id"),
            comment.get("id"),
            metadata.get("comment_id"),
            attachment_data.get("comment_id"),
        ):
            if _clean_string(candidate) == comment_id:
                return True
    return False


def _extract_post_id_from_comment_context(message: Mapping[str, Any]) -> str | None:
    post = _as_mapping(message.get("post"))
    direct_post_id = _first_non_empty_string(message.get("post_id"), post.get("id"))
    if direct_post_id:
        return direct_post_id

    for attachment in _as_list(message.get("attachments")):
        attachment_data = _as_mapping(attachment)
        payload = _as_mapping(attachment_data.get("payload"))
        post_id = _first_non_empty_string(
            attachment_data.get("post_id"),
            payload.get("post_id"),
            _as_mapping(attachment_data.get("post")).get("id"),
        )
        if post_id:
            return post_id
    return None


def _extract_comment_context_description(message: Mapping[str, Any]) -> str | None:
    attachments = _as_list(message.get("attachments"))
    return _first_post_attachment_description(attachments) or _first_attachment_text(attachments)


def extract_page_comment_reply_source_detail(
    normalized: Mapping[str, Any],
    response_data: Any,
) -> dict[str, Any]:
    trigger_message_mid = _clean_string(normalized.get("message_mid"))
    messages = extract_messages_from_pancake_response(response_data)
    notice_message = _find_message_by_id(messages, trigger_message_mid)
    comment_id = (
        extract_comment_id_from_message_tags(_message_tags_from_normalized(normalized))
        or extract_comment_id_from_message_tags(_as_mapping(notice_message).get("message_tags"))
    )
    if not comment_id:
        return {
            "ok": False,
            "reason": "pancake_comment_id_missing",
            "trigger_type": PANCAKE_MESSAGE_PAGE_COMMENT_REPLY_NOTICE,
            "trigger_message_mid": trigger_message_mid,
        }

    comment_context = None
    fallback_context = None
    for message in messages:
        if not _message_contains_comment_id(message, comment_id):
            continue
        if fallback_context is None:
            fallback_context = message
        if _extract_comment_context_description(message):
            comment_context = message
            break

    comment_context = comment_context or fallback_context
    if comment_context is None:
        return {
            "ok": False,
            "reason": "pancake_comment_post_context_missing",
            "trigger_type": PANCAKE_MESSAGE_PAGE_COMMENT_REPLY_NOTICE,
            "trigger_message_mid": trigger_message_mid,
            "comment_id": comment_id,
        }

    description = _extract_comment_context_description(comment_context)
    if not description:
        return {
            "ok": False,
            "reason": "pancake_comment_post_description_missing",
            "trigger_type": PANCAKE_MESSAGE_PAGE_COMMENT_REPLY_NOTICE,
            "trigger_message_mid": trigger_message_mid,
            "comment_id": comment_id,
        }

    return {
        "ok": True,
        "reason": None,
        "trigger_type": PANCAKE_MESSAGE_PAGE_COMMENT_REPLY_NOTICE,
        "trigger_message_mid": trigger_message_mid,
        "comment_id": comment_id,
        "description": description,
        "post_id": _extract_post_id_from_comment_context(comment_context),
    }
