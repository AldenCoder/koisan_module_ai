from app.services import pancake_auto_consult_service as acs


def _normalized_ad_card():
    return {
        "page_id": "page-1",
        "sender_id": "page-1",
        "platform_sender_id": "page-1",
        "message_mid": "ad-123",
        "attachments": [
            {
                "type": "ad_click",
            }
        ],
        "raw": {
            "data": {
                "message": {
                    "id": "ad-123",
                    "message_tags": [],
                }
            }
        },
    }


def _normalized_comment_notice():
    text = "Bạn đang phản hồi bình luận của người dùng về bài viết trên Trang của mình. (Link Facebook)"
    return {
        "page_id": "page-1",
        "sender_id": "page-1",
        "platform_sender_id": "page-1",
        "message_mid": "mid-notice-1",
        "text": text,
        "message_from_admin_name": None,
        "message_from_uid": None,
        "attachments": [],
        "raw": {
            "data": {
                "message": {
                    "id": "mid-notice-1",
                    "message": text,
                    "original_message": (
                        "Bạn đang phản hồi bình luận của người dùng về bài viết trên Trang của mình. "
                        "Xem bình luận..."
                    ),
                    "message_tags": [
                        {
                            "link": "https://facebook.com/page/posts/post-1/?comment_id=comment-1",
                        }
                    ],
                }
            }
        },
    }


def test_is_pancake_ad_card_message_detects_ad_mid():
    assert acs.is_pancake_ad_card_message(_normalized_ad_card()) is True
    assert acs.is_pancake_ad_card_message({"message_mid": "mid-1"}) is False


def test_is_pancake_page_comment_reply_notice_requires_all_signals():
    normalized = _normalized_comment_notice()

    assert acs.is_pancake_page_comment_reply_notice(normalized) is True

    missing_comment_id = _normalized_comment_notice()
    missing_comment_id["raw"]["data"]["message"]["message_tags"] = []
    assert acs.is_pancake_page_comment_reply_notice(missing_comment_id) is False

    customer_sender = _normalized_comment_notice()
    customer_sender["sender_id"] = "customer-1"
    customer_sender["platform_sender_id"] = "customer-1"
    assert acs.is_pancake_page_comment_reply_notice(customer_sender) is False

    with_admin = _normalized_comment_notice()
    with_admin["message_from_admin_name"] = "Admin"
    assert acs.is_pancake_page_comment_reply_notice(with_admin) is False

    with_attachment = _normalized_comment_notice()
    with_attachment["attachments"] = [{"type": "template"}]
    assert acs.is_pancake_page_comment_reply_notice(with_attachment) is False


def test_extract_ad_card_source_detail_happy_path():
    response_data = {
        "messages": [
            {
                "id": "ad-123",
                "attachments": [
                    {
                        "type": "ad_click",
                        "ad_id": "ad-id-1",
                        "post_attachments": [
                            {
                                "description": "Mẫu mới S7671263 và S7672889",
                            }
                        ],
                    }
                ],
            }
        ],
        "ad_clicks": [
            {
                "ad_id": "ad-id-1",
                "post_id": "post-1",
            }
        ],
    }

    result = acs.extract_ad_card_source_detail(_normalized_ad_card(), response_data)

    assert result["ok"] is True
    assert result["trigger_type"] == "ad_card"
    assert result["trigger_message_mid"] == "ad-123"
    assert result["description"] == "Mẫu mới S7671263 và S7672889"
    assert result["ad_id"] == "ad-id-1"
    assert result["post_id"] == "post-1"


def test_extract_ad_card_source_detail_matches_nested_customers_ad_clicks():
    response_data = {
        "data": {
            "messages": [
                {
                    "id": "ad-123",
                    "attachments": [
                        {
                            "type": "ad_click",
                            "ad_id": "ad-id-1",
                            "post_attachments": [
                                {
                                    "description": "Mau S7671263",
                                }
                            ],
                        }
                    ],
                }
            ],
            "customers": [
                {
                    "ad_clicks": [
                        {
                            "ad_id": "ad-id-1",
                            "post_id": "post-from-customer",
                        }
                    ]
                }
            ],
        }
    }

    result = acs.extract_ad_card_source_detail(_normalized_ad_card(), response_data)

    assert result["ok"] is True
    assert result["post_id"] == "post-from-customer"


def test_extract_ad_card_source_detail_returns_missing_reasons():
    normalized = _normalized_ad_card()

    assert acs.extract_ad_card_source_detail(normalized, {"messages": []})["reason"] == "pancake_ad_message_not_found"
    assert (
        acs.extract_ad_card_source_detail(
            normalized,
            {"messages": [{"id": "ad-123", "attachments": []}]},
        )["reason"]
        == "pancake_ad_click_missing"
    )
    assert (
        acs.extract_ad_card_source_detail(
            normalized,
            {"messages": [{"id": "ad-123", "attachments": [{"type": "ad_click"}]}]},
        )["reason"]
        == "pancake_ad_description_missing"
    )


def test_extract_page_comment_reply_source_detail_happy_path():
    response_data = {
        "messages": [
            {
                "id": "mid-context-1",
                "message_tags": [
                    {
                        "link": "https://facebook.com/page/posts/post-1/?comment_id=comment-1",
                    }
                ],
                "post_id": "post-1",
                "attachments": [
                    {
                        "post_attachments": [
                            {
                                "description": "Bài viết có mẫu S7671263",
                            }
                        ]
                    }
                ],
            }
        ],
    }

    result = acs.extract_page_comment_reply_source_detail(_normalized_comment_notice(), response_data)

    assert result["ok"] is True
    assert result["trigger_type"] == "page_comment_reply_notice"
    assert result["trigger_message_mid"] == "mid-notice-1"
    assert result["comment_id"] == "comment-1"
    assert result["description"] == "Bài viết có mẫu S7671263"
    assert result["post_id"] == "post-1"


def test_extract_page_comment_reply_source_detail_uses_notice_fallback_and_comment_metadata():
    normalized = _normalized_comment_notice()
    normalized["raw"]["data"]["message"]["message_tags"] = []
    response_data = {
        "messages": [
            {
                "id": "mid-notice-1",
                "message_tags": [
                    {
                        "link": "https://facebook.com/page/posts/post-1/?comment_id=comment-1",
                    }
                ],
                "attachments": [],
            },
            {
                "id": "mid-context-1",
                "post_id": "post-1",
                "attachments": [
                    {
                        "comment": {
                            "msg_id": "comment-1",
                        },
                        "name": "Mau S7671263",
                    }
                ],
            },
        ],
    }

    result = acs.extract_page_comment_reply_source_detail(normalized, response_data)

    assert result["ok"] is True
    assert result["comment_id"] == "comment-1"
    assert result["description"] == "Mau S7671263"
    assert result["post_id"] == "post-1"


def test_extract_page_comment_reply_source_detail_returns_missing_reasons():
    normalized = _normalized_comment_notice()
    no_comment_id = _normalized_comment_notice()
    no_comment_id["raw"]["data"]["message"]["message_tags"] = []

    assert (
        acs.extract_page_comment_reply_source_detail(no_comment_id, {"messages": []})["reason"]
        == "pancake_comment_id_missing"
    )
    assert (
        acs.extract_page_comment_reply_source_detail(normalized, {"messages": []})["reason"]
        == "pancake_comment_post_context_missing"
    )
    assert (
        acs.extract_page_comment_reply_source_detail(
            normalized,
            {
                "messages": [
                    {
                        "message_tags": [
                            {
                                "link": "https://facebook.com/page/posts/post-1/?comment_id=comment-1",
                            }
                        ],
                        "attachments": [],
                    }
                ]
            },
        )["reason"]
        == "pancake_comment_post_description_missing"
    )


def test_extract_product_codes_dedupes_and_preserves_order():
    description = "Mẫu S7671263, W2651713, S7671263. IDs 123456789 987654321"

    assert acs.extract_product_codes(description) == ["S7671263", "W2651713"]


def test_extract_product_codes_supports_current_sku_formats():
    description = """
    SKU
    w2651703
    S2650529A
    S26505299H
    S2650529-9H
    S2651749 - Q
    S2651749-Q
    W2651713-3
    S2382008 - 7
    500220-1
    S2651755 - PA
    """

    assert acs.extract_product_codes(description) == [
        "w2651703",
        "S2650529A",
        "S26505299H",
        "S2650529-9H",
        "S2651749 - Q",
        "S2651749-Q",
        "W2651713-3",
        "S2382008 - 7",
        "500220-1",
        "S2651755 - PA",
    ]


def test_build_auto_consult_prompt_supports_one_or_many_codes():
    assert acs.build_auto_consult_prompt(["S7671263"]) == {
        "ok": True,
        "reason": None,
        "product_codes": ["S7671263"],
        "product_code_count": 1,
        "product_codes_csv": "S7671263",
        "prompt": "tư vấn mẫu S7671263 và gửi ảnh lookbook",
    }

    result = acs.build_auto_consult_prompt(["S7671263", "S7672889"])
    assert result["prompt"] == "tư vấn mẫu S7671263, S7672889 và gửi ảnh lookbook"


def test_build_auto_consult_prompt_from_description_requires_product_code():
    result = acs.build_auto_consult_prompt_from_description("không có mã mẫu")

    assert result["ok"] is False
    assert result["reason"] == "pancake_product_code_missing"
    assert result["product_codes"] == []


def test_build_customer_comment_ai_message_adds_post_product_codes():
    normalized = {
        "text": "giá",
        "raw": {
            "data": {
                "post": {
                    "message": "Mẫu mới S2650529 đang có sẵn",
                }
            }
        },
    }

    result = acs.build_customer_comment_ai_message(normalized)

    assert result == {
        "content": "giá, tư vấn mã sản phẩm S2650529, và gửi ảnh lookbook",
        "product_codes": ["S2650529"],
        "product_code_count": 1,
        "augmented": True,
        "initial_product_prompt": True,
        "follow_up": False,
        "post_message_present": True,
    }


def test_build_customer_comment_ai_message_keeps_follow_up_comment_text():
    normalized = {
        "text": "oke",
        "raw": {
            "data": {
                "post": {
                    "message": "Mẫu mới S2650529 đang có sẵn",
                }
            }
        },
    }

    result = acs.build_customer_comment_ai_message(
        normalized,
        initial_product_prompt=False,
    )

    assert result["product_codes"] == ["S2650529"]
    assert result["product_code_count"] == 1
    assert result["augmented"] is False
    assert result["initial_product_prompt"] is False
    assert result["follow_up"] is True
    assert result["content"] == "oke"
    assert "tư vấn mã sản phẩm" not in result["content"]
    assert "gửi ảnh lookbook" not in result["content"]


def test_build_customer_comment_ai_message_keeps_comment_when_post_has_no_code():
    normalized = {
        "text": "giá",
        "raw": {
            "data": {
                "post": {
                    "message": "Bộ sưu tập mới",
                }
            }
        },
    }

    result = acs.build_customer_comment_ai_message(normalized)

    assert result == {
        "content": "giá",
        "product_codes": [],
        "product_code_count": 0,
        "augmented": False,
        "initial_product_prompt": False,
        "follow_up": False,
        "post_message_present": True,
    }
