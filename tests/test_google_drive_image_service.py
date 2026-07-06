import asyncio

from app.services.google_drive_image_service import (
    GOOGLE_DRIVE_FILES_URL,
    GOOGLE_DRIVE_FOLDER_MIME_TYPE,
    build_drive_folder_children_query,
    build_drive_files_query,
    build_drive_image_url,
    extract_drive_folder_urls_from_text,
    parse_drive_folder_id,
    split_text_and_drive_folder_urls,
    GoogleDriveImageService,
)
from app.services.pancake_drive_image_color_service import build_requested_color_match


class _FakeDriveResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


class _FakeDriveClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def get(self, url, params):
        self.calls.append({"url": url, "params": params})
        return self.responses.pop(0)


def test_parse_drive_folder_id_supports_query_and_trailing_slash():
    folder_id = parse_drive_folder_id(
        "https://drive.google.com/drive/folders/16lg-E8eT7eeiYtv-X80BgD71AYHvbGNJ/?usp=sharing"
    )

    assert folder_id == "16lg-E8eT7eeiYtv-X80BgD71AYHvbGNJ"


def test_split_text_and_drive_folder_urls_removes_sample_brain_lookbook_link():
    result = split_text_and_drive_folder_urls(
        "Dạ em có thể gửi chị **link lookbook** của mẫu **W2651713** để mình xem ạ:  \n"
        "https://drive.google.com/drive/folders/16lg-E8eT7eeiYtv-X80BgD71AYHvbGNJ 💕  \n"
        "\n"
        "Chị muốn em tư vấn luôn **size** cho mình không ạ?"
    )

    assert result.text == (
        "Dạ em có thể gửi chị **link lookbook** của mẫu **W2651713** để mình xem ạ:\n"
        "\n"
        "Chị muốn em tư vấn luôn **size** cho mình không ạ?"
    )
    assert result.drive_folder_urls == [
        "https://drive.google.com/drive/folders/16lg-E8eT7eeiYtv-X80BgD71AYHvbGNJ"
    ]


def test_extract_drive_folder_urls_from_text_deduplicates_valid_drive_links():
    urls = extract_drive_folder_urls_from_text(
        "Link 1 https://drive.google.com/drive/folders/folder_1 "
        "lặp https://drive.google.com/drive/folders/folder_1 "
        "không lấy https://example.com/drive/folders/folder_2"
    )

    assert urls == ["https://drive.google.com/drive/folders/folder_1"]


def test_parse_drive_folder_id_rejects_invalid_url():
    try:
        parse_drive_folder_id("https://drive.google.com/file/d/not-a-folder/view")
    except ValueError as exc:
        assert str(exc) == "drive_folder_id_not_found"
    else:  # pragma: no cover - defensive
        raise AssertionError("invalid folder URL should raise ValueError")


def test_parse_drive_folder_id_rejects_non_drive_host():
    try:
        parse_drive_folder_id("https://example.com/drive/folders/folder_1")
    except ValueError as exc:
        assert str(exc) == "drive_folder_url_invalid_host"
    else:  # pragma: no cover - defensive
        raise AssertionError("non-drive URL should raise ValueError")


def test_build_drive_files_query_filters_drive_images():
    query = build_drive_files_query("folder_123")

    assert query == (
        "'folder_123' in parents and trashed=false "
        "and (mimeType='image/jpeg' or mimeType='image/png')"
    )


def test_build_drive_folder_children_query_filters_images_and_folders():
    query = build_drive_folder_children_query("folder_123")

    assert query == (
        "'folder_123' in parents and trashed=false "
        "and (mimeType='image/jpeg' or mimeType='image/png' "
        "or mimeType='application/vnd.google-apps.folder')"
    )


def test_build_drive_image_url_uses_lh3_format():
    assert build_drive_image_url("image_123") == "https://lh3.googleusercontent.com/d/image_123"


def test_lookup_folder_images_parses_drive_response_and_converts_urls():
    client = _FakeDriveClient(
        [
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "jpeg_1",
                            "name": "one.jpg",
                            "mimeType": "image/jpeg",
                            "size": "123",
                        },
                        {
                            "id": "png_2",
                            "name": "two.png",
                            "mimeType": "image/png",
                        },
                        {
                            "id": "html_ignored",
                            "name": "not-image.html",
                            "mimeType": "text/html",
                        },
                        {
                            "name": "missing-id.jpg",
                            "mimeType": "image/jpeg",
                        },
                    ]
                }
            )
        ]
    )
    service = GoogleDriveImageService(api_key="drive-key", client=client)

    result = asyncio.run(
        service.lookup_folder_images(["https://drive.google.com/drive/folders/folder_123"])
    )

    assert client.calls[0]["url"] == GOOGLE_DRIVE_FILES_URL
    assert client.calls[0]["params"]["key"] == "drive-key"
    assert client.calls[0]["params"]["q"] == build_drive_files_query("folder_123")
    assert client.calls[0]["params"]["fields"] == "nextPageToken,files(id,name,mimeType,size)"
    assert result[0].folder_id == "folder_123"
    assert result[0].error is None
    assert [image.imageUrl for image in result[0].images] == [
        "https://lh3.googleusercontent.com/d/jpeg_1",
        "https://lh3.googleusercontent.com/d/png_2",
    ]
    assert result[0].images[0].name == "one.jpg"
    assert result[0].images[0].size == "123"


def test_lookup_folder_images_keeps_folder_level_errors_in_batch():
    client = _FakeDriveClient(
        [
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "ok_1",
                            "name": "ok.jpg",
                            "mimeType": "image/jpeg",
                        }
                    ]
                }
            )
        ]
    )
    service = GoogleDriveImageService(api_key="drive-key", client=client)

    result = asyncio.run(
        service.lookup_folder_images(
            [
                "https://drive.google.com/drive/folders/ok_folder",
                "https://example.com/not-drive-folder",
            ]
        )
    )

    assert result[0].folder_id == "ok_folder"
    assert result[0].images[0].imageUrl == "https://lh3.googleusercontent.com/d/ok_1"
    assert result[1].folder_id is None
    assert result[1].error == "drive_folder_url_invalid_host"


def test_lookup_folder_images_returns_http_error_per_folder():
    client = _FakeDriveClient([_FakeDriveResponse(status_code=403, payload={}, text="forbidden")])
    service = GoogleDriveImageService(api_key="drive-key", client=client)

    result = asyncio.run(
        service.lookup_folder_images(["https://drive.google.com/drive/folders/private_folder"])
    )

    assert result[0].folder_id == "private_folder"
    assert result[0].images == []
    assert result[0].error == "drive_api_http_403"


def test_lookup_folder_images_nested_returns_root_images_without_descending():
    client = _FakeDriveClient(
        [
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "image_1",
                            "name": "one.jpg",
                            "mimeType": "image/jpeg",
                        },
                    ]
                }
            )
        ]
    )
    service = GoogleDriveImageService(api_key="drive-key", client=client)

    result = asyncio.run(
        service.lookup_folder_images_nested(
            ["https://drive.google.com/drive/folders/root_folder"],
            max_depth=3,
        )
    )

    assert len(client.calls) == 1
    assert client.calls[0]["params"]["q"] == build_drive_folder_children_query("root_folder")
    assert result[0].folder_id == "root_folder"
    assert result[0].lookup_depth == 1
    assert result[0].visited_folder_ids == ["root_folder"]
    assert result[0].selected_child_folder_ids == []
    assert result[0].error is None
    assert [image.id for image in result[0].images] == ["image_1"]


def test_lookup_folder_images_nested_root_random_can_descend_when_images_and_child_folders(monkeypatch):
    client = _FakeDriveClient(
        [
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "root_image_1",
                            "name": "root.jpg",
                            "mimeType": "image/jpeg",
                        },
                        {
                            "id": "child_1",
                            "name": "Child 1",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        },
                    ]
                }
            ),
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "child_image_1",
                            "name": "child.jpg",
                            "mimeType": "image/jpeg",
                        }
                    ]
                }
            ),
        ]
    )

    def choose(items):
        values = list(items)
        if values == ["images", "child_folders"]:
            return "child_folders"
        return values[0]

    monkeypatch.setattr("app.services.google_drive_image_service.random.choice", choose)
    service = GoogleDriveImageService(api_key="drive-key", client=client)

    result = asyncio.run(
        service.lookup_folder_images_nested(
            ["https://drive.google.com/drive/folders/root_folder"],
            max_depth=3,
        )
    )

    assert len(client.calls) == 2
    assert client.calls[1]["params"]["q"] == build_drive_folder_children_query("child_1")
    assert result[0].selected_group == "images"
    assert result[0].root_selected_group == "child_folders"
    assert result[0].visited_folder_ids == ["root_folder", "child_1"]
    assert result[0].selected_child_folder_ids == ["child_1"]
    assert [image.id for image in result[0].images] == ["child_image_1"]


def test_lookup_folder_images_nested_root_random_can_use_root_images(monkeypatch):
    client = _FakeDriveClient(
        [
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "root_image_1",
                            "name": "root.jpg",
                            "mimeType": "image/jpeg",
                        },
                        {
                            "id": "child_1",
                            "name": "Child 1",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        },
                    ]
                }
            )
        ]
    )

    def choose(items):
        values = list(items)
        if values == ["images", "child_folders"]:
            return "images"
        return values[0]

    monkeypatch.setattr("app.services.google_drive_image_service.random.choice", choose)
    service = GoogleDriveImageService(api_key="drive-key", client=client)

    result = asyncio.run(
        service.lookup_folder_images_nested(
            ["https://drive.google.com/drive/folders/root_folder"],
            max_depth=3,
        )
    )

    assert len(client.calls) == 1
    assert result[0].selected_group == "root_images"
    assert result[0].root_selected_group == "images"
    assert result[0].selected_child_folder_ids == []
    assert [image.id for image in result[0].images] == ["root_image_1"]


def test_lookup_folder_images_nested_skips_child_folders_with_video_in_name():
    client = _FakeDriveClient(
        [
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "blocked_video_folder",
                            "name": "Video Lookbook",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        }
                    ]
                }
            )
        ]
    )
    service = GoogleDriveImageService(api_key="drive-key", client=client)

    result = asyncio.run(
        service.lookup_folder_images_nested(
            ["https://drive.google.com/drive/folders/root_folder"],
            max_depth=3,
        )
    )

    assert len(client.calls) == 1
    assert result[0].images == []
    assert result[0].error == "drive_folder_no_images"
    assert result[0].visited_folder_ids == ["root_folder"]
    assert result[0].selected_child_folder_ids == []


def test_lookup_folder_images_nested_depth_two_uses_images_without_randoming_deeper(monkeypatch):
    client = _FakeDriveClient(
        [
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "child_1",
                            "name": "Child 1",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        }
                    ]
                }
            ),
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "child_image_1",
                            "name": "child.jpg",
                            "mimeType": "image/jpeg",
                        },
                        {
                            "id": "grandchild_1",
                            "name": "Grandchild 1",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        },
                    ]
                }
            ),
        ]
    )
    monkeypatch.setattr(
        "app.services.google_drive_image_service.random.choice",
        lambda items: list(items)[0],
    )
    service = GoogleDriveImageService(api_key="drive-key", client=client)

    result = asyncio.run(
        service.lookup_folder_images_nested(
            ["https://drive.google.com/drive/folders/root_folder"],
            max_depth=3,
        )
    )

    assert len(client.calls) == 2
    assert result[0].lookup_depth == 2
    assert result[0].selected_group == "images"
    assert result[0].selected_child_folder_ids == ["child_1"]
    assert [image.id for image in result[0].images] == ["child_image_1"]


def test_lookup_folder_images_nested_descends_to_child_folder():
    client = _FakeDriveClient(
        [
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "child_1",
                            "name": "Child 1",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        }
                    ]
                }
            ),
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "image_1",
                            "name": "one.jpg",
                            "mimeType": "image/jpeg",
                        }
                    ]
                }
            ),
        ]
    )
    service = GoogleDriveImageService(api_key="drive-key", client=client)

    result = asyncio.run(
        service.lookup_folder_images_nested(
            ["https://drive.google.com/drive/folders/root_folder"],
            max_depth=3,
        )
    )

    assert len(client.calls) == 2
    assert client.calls[0]["params"]["q"] == build_drive_folder_children_query("root_folder")
    assert client.calls[1]["params"]["q"] == build_drive_folder_children_query("child_1")
    assert result[0].lookup_depth == 2
    assert result[0].visited_folder_ids == ["root_folder", "child_1"]
    assert result[0].selected_child_folder_ids == ["child_1"]
    assert result[0].error is None
    assert [image.id for image in result[0].images] == ["image_1"]


def test_lookup_folder_images_nested_randoms_one_child_and_does_not_try_sibling(monkeypatch):
    client = _FakeDriveClient(
        [
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "child_empty",
                            "name": "Empty",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        },
                        {
                            "id": "child_with_image",
                            "name": "With Image",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        },
                    ]
                }
            ),
            _FakeDriveResponse(payload={"files": []}),
        ]
    )
    monkeypatch.setattr(
        "app.services.google_drive_image_service.random.choice",
        lambda folders: folders[0],
    )
    service = GoogleDriveImageService(api_key="drive-key", client=client)

    result = asyncio.run(
        service.lookup_folder_images_nested(
            ["https://drive.google.com/drive/folders/root_folder"],
            max_depth=3,
        )
    )

    assert len(client.calls) == 2
    assert client.calls[1]["params"]["q"] == build_drive_folder_children_query("child_empty")
    assert result[0].images == []
    assert result[0].error == "drive_folder_no_images"
    assert result[0].visited_folder_ids == ["root_folder", "child_empty"]
    assert result[0].selected_child_folder_ids == ["child_empty"]


def test_lookup_folder_images_nested_opens_all_root_color_folders_and_inherits_colors():
    client = _FakeDriveClient(
        [
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "root_image_1",
                            "name": "root.jpg",
                            "mimeType": "image/jpeg",
                        },
                        {
                            "id": "folder_be",
                            "name": "S2650543 BE",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        },
                        {
                            "id": "folder_xanh",
                            "name": "xanh",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        },
                        {
                            "id": "folder_tim",
                            "name": "tím",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        },
                    ]
                }
            ),
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "be_1",
                            "name": "lookbook_1.jpg",
                            "mimeType": "image/jpeg",
                        }
                    ]
                }
            ),
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "xanh_1",
                            "name": "lookbook_1.jpg",
                            "mimeType": "image/jpeg",
                        },
                        {
                            "id": "xanh_2",
                            "name": "lookbook_2.jpg",
                            "mimeType": "image/jpeg",
                        },
                    ]
                }
            ),
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "tim_1",
                            "name": "lookbook_1.jpg",
                            "mimeType": "image/jpeg",
                        }
                    ]
                }
            ),
        ]
    )
    service = GoogleDriveImageService(api_key="drive-key", client=client)

    result = asyncio.run(
        service.lookup_folder_images_nested(
            ["https://drive.google.com/drive/folders/root_folder"],
            max_depth=3,
        )
    )

    assert len(client.calls) == 4
    assert [call["params"]["q"] for call in client.calls] == [
        build_drive_folder_children_query("root_folder"),
        build_drive_folder_children_query("folder_be"),
        build_drive_folder_children_query("folder_xanh"),
        build_drive_folder_children_query("folder_tim"),
    ]
    assert result[0].error is None
    assert result[0].selected_group == "color_diverse_images"
    assert result[0].visited_folder_ids == [
        "root_folder",
        "folder_be",
        "folder_xanh",
        "folder_tim",
    ]
    assert result[0].selected_child_folder_ids == [
        "folder_be",
        "folder_xanh",
        "folder_tim",
    ]
    assert [image.id for image in result[0].images] == [
        "be_1",
        "xanh_1",
        "xanh_2",
        "tim_1",
        "root_image_1",
    ]
    assert [image.drive_file_color for image in result[0].images] == [
        "be",
        "xanh",
        "xanh",
        "tim",
        None,
    ]


def test_lookup_folder_images_nested_skips_empty_color_folder_and_keeps_other_colors():
    client = _FakeDriveClient(
        [
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "folder_be",
                            "name": "BE",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        },
                        {
                            "id": "folder_den",
                            "name": "ĐEN",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        },
                    ]
                }
            ),
            _FakeDriveResponse(payload={"files": []}),
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "den_1",
                            "name": "lookbook.jpg",
                            "mimeType": "image/jpeg",
                        }
                    ]
                }
            ),
        ]
    )
    service = GoogleDriveImageService(api_key="drive-key", client=client)

    result = asyncio.run(
        service.lookup_folder_images_nested(
            ["https://drive.google.com/drive/folders/root_folder"],
            max_depth=3,
        )
    )

    assert len(client.calls) == 3
    assert result[0].error is None
    assert result[0].selected_group == "color_diverse_images"
    assert result[0].visited_folder_ids == ["root_folder", "folder_be", "folder_den"]
    assert result[0].selected_child_folder_ids == ["folder_den"]
    assert [image.id for image in result[0].images] == ["den_1"]
    assert result[0].images[0].drive_file_color == "den"


def test_lookup_folder_images_nested_requested_color_uses_root_matching_image():
    client = _FakeDriveClient(
        [
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "root_do",
                            "name": "vay_da_hoi_do.jpg",
                            "mimeType": "image/jpeg",
                        },
                        {
                            "id": "child_den",
                            "name": "màu đen",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        },
                    ]
                }
            )
        ]
    )
    service = GoogleDriveImageService(api_key="drive-key", client=client)

    result = asyncio.run(
        service.lookup_folder_images_nested(
            ["https://drive.google.com/drive/folders/root_folder"],
            max_depth=3,
            requested_color="do",
        )
    )

    assert len(client.calls) == 1
    assert result[0].requested_color == "do"
    assert result[0].selected_group == "root_color_images"
    assert result[0].color_fallback_used is False
    assert [image.id for image in result[0].images] == ["root_do"]
    assert result[0].images[0].drive_file_color == "do"


def test_lookup_folder_images_nested_requested_color_uses_matching_folder_and_inherits_color():
    client = _FakeDriveClient(
        [
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "root_den",
                            "name": "vay_da_hoi_den.jpg",
                            "mimeType": "image/jpeg",
                        },
                        {
                            "id": "child_do",
                            "name": "màu đỏ",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        },
                    ]
                }
            ),
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "child_image_1",
                            "name": "lookbook_1.jpg",
                            "mimeType": "image/jpeg",
                        }
                    ]
                }
            ),
        ]
    )
    service = GoogleDriveImageService(api_key="drive-key", client=client)

    result = asyncio.run(
        service.lookup_folder_images_nested(
            ["https://drive.google.com/drive/folders/root_folder"],
            max_depth=3,
            requested_color="do",
        )
    )

    assert len(client.calls) == 2
    assert client.calls[1]["params"]["q"] == build_drive_folder_children_query("child_do")
    assert result[0].selected_group == "color_images"
    assert result[0].selected_child_folder_ids == ["child_do"]
    assert [image.id for image in result[0].images] == ["child_image_1"]
    assert result[0].images[0].drive_file_color == "do"
    assert result[0].to_dict()["images"][0]["drive_file_color"] == "do"


def test_lookup_folder_images_nested_requested_color_terms_match_dynamic_folder_name():
    color_match = build_requested_color_match("Em gửi chị ảnh màu Hồng sen ạ", has_drive_link=True)
    client = _FakeDriveClient(
        [
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "root_den",
                            "name": "vay_da_hoi_den.jpg",
                            "mimeType": "image/jpeg",
                        },
                        {
                            "id": "child_hong_sen",
                            "name": "Lookbook Hồng sen",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        },
                    ]
                }
            ),
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "child_image_1",
                            "name": "lookbook_1.jpg",
                            "mimeType": "image/jpeg",
                        }
                    ]
                }
            ),
        ]
    )
    service = GoogleDriveImageService(api_key="drive-key", client=client)

    result = asyncio.run(
        service.lookup_folder_images_nested(
            ["https://drive.google.com/drive/folders/root_folder"],
            max_depth=3,
            requested_color=color_match.primary,
            requested_color_terms=color_match.terms,
        )
    )

    assert len(client.calls) == 2
    assert client.calls[1]["params"]["q"] == build_drive_folder_children_query("child_hong_sen")
    assert result[0].selected_child_folder_ids == ["child_hong_sen"]
    assert result[0].images[0].drive_file_color == "hong"
    assert result[0].to_dict()["requested_color_terms"]


def test_lookup_folder_images_nested_requested_color_terms_match_dynamic_file_token():
    color_match = build_requested_color_match("Em gửi chị ảnh màu Hồng sen ạ", has_drive_link=True)
    client = _FakeDriveClient(
        [
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "root_hong",
                            "name": "lookbook_hong_style.jpg",
                            "mimeType": "image/jpeg",
                        },
                        {
                            "id": "root_den",
                            "name": "lookbook_den.jpg",
                            "mimeType": "image/jpeg",
                        },
                    ]
                }
            )
        ]
    )
    service = GoogleDriveImageService(api_key="drive-key", client=client)

    result = asyncio.run(
        service.lookup_folder_images_nested(
            ["https://drive.google.com/drive/folders/root_folder"],
            max_depth=3,
            requested_color=color_match.primary,
            requested_color_terms=color_match.terms,
        )
    )

    assert len(client.calls) == 1
    assert result[0].selected_group == "color_images"
    assert [image.id for image in result[0].images] == ["root_hong"]
    assert result[0].images[0].drive_file_color == "hongsen"


def test_lookup_folder_images_nested_requested_color_randoms_between_matching_image_and_folder(monkeypatch):
    client = _FakeDriveClient(
        [
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "root_do",
                            "name": "vay_da_hoi_do.jpg",
                            "mimeType": "image/jpeg",
                        },
                        {
                            "id": "child_do",
                            "name": "màu đỏ",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        },
                    ]
                }
            ),
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "child_image_1",
                            "name": "lookbook.jpg",
                            "mimeType": "image/jpeg",
                        }
                    ]
                }
            ),
        ]
    )

    def choose(items):
        values = list(items)
        if values == ["images", "child_folders"]:
            return "child_folders"
        return values[0]

    monkeypatch.setattr("app.services.google_drive_image_service.random.choice", choose)
    service = GoogleDriveImageService(api_key="drive-key", client=client)

    result = asyncio.run(
        service.lookup_folder_images_nested(
            ["https://drive.google.com/drive/folders/root_folder"],
            max_depth=3,
            requested_color="do",
        )
    )

    assert len(client.calls) == 2
    assert result[0].root_selected_group == "child_folders"
    assert result[0].selected_group == "color_images"
    assert result[0].selected_child_folder_ids == ["child_do"]
    assert [image.id for image in result[0].images] == ["child_image_1"]
    assert result[0].images[0].drive_file_color == "do"


def test_lookup_folder_images_nested_requested_color_root_no_match_can_use_root_images_as_fallback(monkeypatch):
    client = _FakeDriveClient(
        [
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "root_den",
                            "name": "vay_da_hoi_den.jpg",
                            "mimeType": "image/jpeg",
                        },
                        {
                            "id": "child_xanh",
                            "name": "màu xanh",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        },
                    ]
                }
            )
        ]
    )

    def choose(items):
        values = list(items)
        if values == ["images", "child_folders"]:
            return "images"
        return values[0]

    monkeypatch.setattr("app.services.google_drive_image_service.random.choice", choose)
    service = GoogleDriveImageService(api_key="drive-key", client=client)

    result = asyncio.run(
        service.lookup_folder_images_nested(
            ["https://drive.google.com/drive/folders/root_folder"],
            max_depth=3,
            requested_color="hong",
        )
    )

    assert len(client.calls) == 1
    assert result[0].root_selected_group == "images"
    assert result[0].selected_group == "root_fallback_images"
    assert result[0].color_fallback_used is True
    assert [image.id for image in result[0].images] == ["root_den"]


def test_lookup_folder_images_nested_requested_color_falls_back_within_visited_branch(monkeypatch):
    client = _FakeDriveClient(
        [
            _FakeDriveResponse(
                payload={
                    "nextPageToken": "ignored-page",
                    "files": [
                        {
                            "id": "root_den",
                            "name": "vay_da_hoi_den.jpg",
                            "mimeType": "image/jpeg",
                        },
                        {
                            "id": "child_empty",
                            "name": "Child Empty",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        },
                        {
                            "id": "sibling_do",
                            "name": "màu đỏ",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        },
                    ],
                }
            ),
            _FakeDriveResponse(payload={"files": []}),
        ]
    )

    def choose(items):
        values = list(items)
        if values == ["images", "child_folders"]:
            return "child_folders"
        return values[0]

    monkeypatch.setattr("app.services.google_drive_image_service.random.choice", choose)
    service = GoogleDriveImageService(api_key="drive-key", client=client)

    result = asyncio.run(
        service.lookup_folder_images_nested(
            ["https://drive.google.com/drive/folders/root_folder"],
            max_depth=3,
            requested_color="hong",
        )
    )

    assert len(client.calls) == 2
    assert "pageToken" not in client.calls[0]["params"]
    assert client.calls[1]["params"]["q"] == build_drive_folder_children_query("child_empty")
    assert result[0].page_truncated is True
    assert result[0].color_fallback_used is True
    assert result[0].selected_group == "fallback_images"
    assert result[0].root_selected_group == "child_folders"
    assert result[0].visited_folder_ids == ["root_folder", "child_empty"]
    assert result[0].selected_child_folder_ids == ["child_empty"]
    assert [image.id for image in result[0].images] == ["root_den"]


def test_lookup_folder_images_nested_stops_at_depth_limit():
    client = _FakeDriveClient(
        [
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "child_1",
                            "name": "Child 1",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        }
                    ]
                }
            ),
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "child_2",
                            "name": "Child 2",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        }
                    ]
                }
            ),
            _FakeDriveResponse(
                payload={
                    "files": [
                        {
                            "id": "child_3",
                            "name": "Child 3",
                            "mimeType": GOOGLE_DRIVE_FOLDER_MIME_TYPE,
                        }
                    ]
                }
            ),
        ]
    )
    service = GoogleDriveImageService(api_key="drive-key", client=client)

    result = asyncio.run(
        service.lookup_folder_images_nested(
            ["https://drive.google.com/drive/folders/root_folder"],
            max_depth=3,
        )
    )

    assert len(client.calls) == 3
    assert result[0].images == []
    assert result[0].error == "drive_folder_no_images_within_depth_limit"
    assert result[0].lookup_depth == 3
    assert result[0].visited_folder_ids == ["root_folder", "child_1", "child_2"]
    assert result[0].selected_child_folder_ids == ["child_1", "child_2"]


def test_lookup_folder_images_nested_does_not_follow_next_page_token():
    client = _FakeDriveClient(
        [
            _FakeDriveResponse(
                payload={
                    "nextPageToken": "next-page",
                    "files": [
                        {
                            "id": "image_1",
                            "name": "one.jpg",
                            "mimeType": "image/jpeg",
                        }
                    ],
                }
            )
        ]
    )
    service = GoogleDriveImageService(api_key="drive-key", client=client)

    result = asyncio.run(
        service.lookup_folder_images_nested(
            ["https://drive.google.com/drive/folders/root_folder"],
            max_depth=3,
        )
    )

    assert len(client.calls) == 1
    assert "pageToken" not in client.calls[0]["params"]
    assert result[0].page_truncated is True
    assert result[0].to_dict()["page_truncated"] is True
    assert [image.id for image in result[0].images] == ["image_1"]
