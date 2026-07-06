import asyncio
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.api.dependencies.error_codes import ErrorCode
from app.services import image_asset_service as service
from app.services.image_asset_service import (
    ImageAssetProcessingError,
    StoredImage,
    create_image_asset_service,
    delete_image_asset_service,
    get_image_asset_by_code_service,
    get_image_asset_service,
    list_image_assets_service,
    update_image_asset_service,
)


class _FakeQuery:
    def __init__(self, records, filters):
        self.records = list(records)
        self.filters = filters
        self.skip_value = 0
        self.limit_value = None
        self.sort_value = None

    async def count(self):
        return len(self._matched())

    def sort(self, value):
        self.sort_value = value
        return self

    def skip(self, value):
        self.skip_value = value
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    async def to_list(self):
        records = self._matched()
        if self.sort_value == "-updated_at":
            records.sort(key=lambda item: item.updated_at, reverse=True)
        end = (
            self.skip_value + self.limit_value
            if self.limit_value is not None
            else None
        )
        return records[self.skip_value:end]

    def _matched(self):
        records = list(self.records)
        code = self.filters.get("code")
        if code is not None:
            records = [item for item in records if item.code == code]
        or_filters = self.filters.get("$or")
        if or_filters:
            patterns = [
                re.compile(entry[field]["$regex"], re.IGNORECASE)
                for entry in or_filters
                for field in entry
            ]
            records = [
                item
                for item in records
                if any(
                    pattern.search(item.code)
                    or pattern.search(item.description or "")
                    for pattern in patterns
                )
            ]
        return records


class _FakeImageAsset:
    records = []
    insert_error = None

    def __init__(
        self,
        *,
        code,
        description,
        url_images,
        id=None,
        created_at=None,
        updated_at=None,
    ):
        now = datetime.now(timezone.utc)
        self.id = id or ObjectId()
        self.code = code
        self.description = description
        self.url_images = list(url_images)
        self.created_at = created_at or now
        self.updated_at = updated_at or now
        self.save_error = None
        self.deleted = False

    @classmethod
    async def find_one(cls, filters):
        for record in cls.records:
            id_filter = filters.get("_id")
            if id_filter is not None and not isinstance(id_filter, dict):
                if record.id != id_filter:
                    continue
            if "code" in filters and record.code != filters["code"]:
                continue
            not_id = id_filter.get("$ne") if isinstance(id_filter, dict) else None
            if not_id is not None and record.id == not_id:
                continue
            return record
        return None

    @classmethod
    def find(cls, filters):
        return _FakeQuery(cls.records, filters)

    async def insert(self):
        if type(self).insert_error is not None:
            raise type(self).insert_error
        type(self).records.append(self)
        return self

    async def save(self):
        if self.save_error is not None:
            raise self.save_error
        return self

    async def delete(self):
        self.deleted = True
        type(self).records.remove(self)


class _ClosableUpload:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def fake_image_asset_model(monkeypatch):
    _FakeImageAsset.records = []
    _FakeImageAsset.insert_error = None
    monkeypatch.setattr(service, "ImageAsset", _FakeImageAsset)
    monkeypatch.setattr(service.settings, "base_url", "http://localhost:8000")


def _stored_image(tmp_path, file_name, public_url=None):
    local_path = tmp_path / file_name
    local_path.write_bytes(b"stored-image")
    return StoredImage(
        file_name=file_name,
        local_path=local_path,
        public_url=public_url or f"http://localhost:8000/rag-images/{file_name}",
        original_size=100,
        stored_size=12,
        width=100,
        height=50,
        preferred_target_met=True,
    )


def _record(
    *,
    code="CODE",
    description=None,
    file_names=("CODE_aaaaaaaaaaaaaaaaaaaa.jpg",),
    updated_at=None,
):
    record = _FakeImageAsset(
        code=code,
        description=description,
        url_images=[
            f"http://localhost:8000/rag-images/{file_name}"
            for file_name in file_names
        ],
        updated_at=updated_at,
    )
    _FakeImageAsset.records.append(record)
    return record


def test_create_service_inserts_record_and_preserves_upload_order(tmp_path, monkeypatch):
    stored = [
        _stored_image(tmp_path, "CODE_aaaaaaaaaaaaaaaaaaaa.jpg"),
        _stored_image(tmp_path, "CODE_bbbbbbbbbbbbbbbbbbbb.jpg"),
    ]
    store_mock = AsyncMock(return_value=stored)
    monkeypatch.setattr(service, "store_upload_batch", store_mock)

    result = asyncio.run(
        create_image_asset_service(
            code=" code ",
            description="  Product images ",
            uploads=[object(), object()],
            storage_dir=tmp_path,
        )
    )

    assert result.code == "CODE"
    assert result.description == "Product images"
    assert result.url_images == [item.public_url for item in stored]
    assert len(_FakeImageAsset.records) == 1
    store_mock.assert_awaited_once()


def test_create_service_returns_conflict_before_writing_files(monkeypatch):
    _record(code="CODE")
    store_mock = AsyncMock()
    monkeypatch.setattr(service, "store_upload_batch", store_mock)
    upload = _ClosableUpload()

    with pytest.raises(ImageAssetProcessingError) as exc:
        asyncio.run(
            create_image_asset_service(
                code="code",
                description=None,
                uploads=[upload],
            )
        )

    assert exc.value.status_code == 409
    assert exc.value.error_code == ErrorCode.IMAGE_ASSET_CODE_EXISTS
    store_mock.assert_not_awaited()
    assert upload.closed is True


def test_create_service_rolls_back_files_on_duplicate_race(tmp_path, monkeypatch):
    stored = [_stored_image(tmp_path, "CODE_aaaaaaaaaaaaaaaaaaaa.jpg")]
    monkeypatch.setattr(service, "store_upload_batch", AsyncMock(return_value=stored))
    _FakeImageAsset.insert_error = DuplicateKeyError("duplicate")

    with pytest.raises(ImageAssetProcessingError) as exc:
        asyncio.run(
            create_image_asset_service(
                code="CODE",
                description=None,
                uploads=[object()],
                storage_dir=tmp_path,
            )
        )

    assert exc.value.status_code == 409
    assert not stored[0].local_path.exists()


def test_create_service_rolls_back_files_on_database_error(tmp_path, monkeypatch):
    stored = [_stored_image(tmp_path, "CODE_aaaaaaaaaaaaaaaaaaaa.jpg")]
    monkeypatch.setattr(service, "store_upload_batch", AsyncMock(return_value=stored))
    _FakeImageAsset.insert_error = RuntimeError("database unavailable")

    with pytest.raises(ImageAssetProcessingError) as exc:
        asyncio.run(
            create_image_asset_service(
                code="CODE",
                description=None,
                uploads=[object()],
                storage_dir=tmp_path,
            )
        )

    assert exc.value.status_code == 500
    assert not stored[0].local_path.exists()


def test_list_service_filters_escapes_keyword_and_sorts():
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    new = old + timedelta(days=1)
    _record(code="A.1", description=None, updated_at=old)
    _record(
        code="B",
        description="Contains A.1 literally",
        file_names=("B_bbbbbbbbbbbbbbbbbbbb.jpg",),
        updated_at=new,
    )
    _record(
        code="AX1",
        description="regex lookalike",
        file_names=("AX1_cccccccccccccccccccc.jpg",),
        updated_at=new,
    )

    result = asyncio.run(
        list_image_assets_service(page=1, size=10, keyword="A.1")
    )

    assert [item.code for item in result.items] == ["B", "A.1"]
    assert result.total == 2


def test_list_service_supports_exact_normalized_code_and_pagination():
    _record(code="CODE")
    _record(code="OTHER", file_names=("OTHER_bbbbbbbbbbbbbbbbbbbb.jpg",))

    result = asyncio.run(
        list_image_assets_service(page=1, size=1, code=" code ")
    )

    assert result.total == 1
    assert [item.code for item in result.items] == ["CODE"]


def test_list_service_defaults_return_newest_first():
    old = datetime(2025, 1, 1, tzinfo=timezone.utc)
    new = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _record(code="OLD", updated_at=old)
    _record(
        code="NEW",
        file_names=("NEW_bbbbbbbbbbbbbbbbbbbb.jpg",),
        updated_at=new,
    )

    result = asyncio.run(list_image_assets_service())

    assert [item.code for item in result.items] == ["NEW", "OLD"]
    assert result.page == 1
    assert result.size == 10


def test_detail_and_by_code_service_map_invalid_and_missing_records():
    record = _record(code="CODE")

    detail = asyncio.run(get_image_asset_service(str(record.id)))
    by_code = asyncio.run(get_image_asset_by_code_service(" code "))

    assert detail.id == str(record.id)
    assert by_code.code == "CODE"

    with pytest.raises(ImageAssetProcessingError) as invalid:
        asyncio.run(get_image_asset_service("bad-id"))
    assert invalid.value.status_code == 400

    with pytest.raises(ImageAssetProcessingError) as missing:
        asyncio.run(get_image_asset_service(str(ObjectId())))
    assert missing.value.status_code == 404


def test_update_metadata_and_clear_description():
    record = _record(
        description="Old",
        updated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    previous_updated_at = record.updated_at

    result = asyncio.run(
        update_image_asset_service(
            str(record.id),
            description="",
        )
    )

    assert result.description is None
    assert record.description is None
    assert record.updated_at > previous_updated_at


def test_update_rejects_empty_request_unknown_image_and_empty_result():
    record = _record()

    with pytest.raises(ImageAssetProcessingError) as empty_update:
        asyncio.run(update_image_asset_service(str(record.id)))
    assert empty_update.value.error_code == ErrorCode.IMAGE_ASSET_EMPTY_UPDATE

    with pytest.raises(ImageAssetProcessingError) as unknown_image:
        asyncio.run(
            update_image_asset_service(
                str(record.id),
                remove_image_file_names=["UNKNOWN.jpg"],
            )
        )
    assert unknown_image.value.error_code == ErrorCode.IMAGE_ASSET_IMAGE_NOT_FOUND

    with pytest.raises(ImageAssetProcessingError) as empty_result:
        asyncio.run(
            update_image_asset_service(
                str(record.id),
                remove_image_file_names=["CODE_aaaaaaaaaaaaaaaaaaaa.jpg"],
            )
        )
    assert empty_result.value.status_code == 422


def test_update_code_renames_files_preserves_random_id_and_updates_url(tmp_path):
    old_name = "OLD_aaaaaaaaaaaaaaaaaaaa.jpg"
    new_name = "NEW_aaaaaaaaaaaaaaaaaaaa.jpg"
    (tmp_path / old_name).write_bytes(b"old")
    record = _record(code="OLD", file_names=(old_name,))

    result = asyncio.run(
        update_image_asset_service(
            str(record.id),
            code="new",
            storage_dir=tmp_path,
        )
    )

    assert result.code == "NEW"
    assert result.url_images == [f"http://localhost:8000/rag-images/{new_name}"]
    assert not (tmp_path / old_name).exists()
    assert (tmp_path / new_name).read_bytes() == b"old"


def test_update_code_rolls_back_rename_when_database_save_fails(tmp_path):
    old_name = "OLD_aaaaaaaaaaaaaaaaaaaa.jpg"
    new_name = "NEW_aaaaaaaaaaaaaaaaaaaa.jpg"
    (tmp_path / old_name).write_bytes(b"old")
    record = _record(code="OLD", file_names=(old_name,))
    record.save_error = RuntimeError("save failed")

    with pytest.raises(RuntimeError):
        asyncio.run(
            update_image_asset_service(
                str(record.id),
                code="NEW",
                storage_dir=tmp_path,
            )
        )

    assert record.code == "OLD"
    assert (tmp_path / old_name).exists()
    assert not (tmp_path / new_name).exists()


def test_update_code_duplicate_returns_conflict_without_renaming(tmp_path):
    old_name = "OLD_aaaaaaaaaaaaaaaaaaaa.jpg"
    (tmp_path / old_name).write_bytes(b"old")
    record = _record(code="OLD", file_names=(old_name,))
    _record(code="TAKEN", file_names=("TAKEN_bbbbbbbbbbbbbbbbbbbb.jpg",))
    upload = _ClosableUpload()

    with pytest.raises(ImageAssetProcessingError) as exc:
        asyncio.run(
            update_image_asset_service(
                str(record.id),
                code="taken",
                uploads=[upload],
                storage_dir=tmp_path,
            )
        )

    assert exc.value.status_code == 409
    assert (tmp_path / old_name).exists()
    assert upload.closed is True


def test_update_duplicate_race_rolls_back_rename(tmp_path):
    old_name = "OLD_aaaaaaaaaaaaaaaaaaaa.jpg"
    new_name = "NEW_aaaaaaaaaaaaaaaaaaaa.jpg"
    (tmp_path / old_name).write_bytes(b"old")
    record = _record(code="OLD", file_names=(old_name,))
    record.save_error = DuplicateKeyError("duplicate")

    with pytest.raises(ImageAssetProcessingError) as exc:
        asyncio.run(
            update_image_asset_service(
                str(record.id),
                code="NEW",
                storage_dir=tmp_path,
            )
        )

    assert exc.value.status_code == 409
    assert (tmp_path / old_name).exists()
    assert not (tmp_path / new_name).exists()


def test_update_partial_rename_failure_rolls_back_previous_files(
    tmp_path,
    monkeypatch,
):
    first_old = "OLD_aaaaaaaaaaaaaaaaaaaa.jpg"
    second_old = "OLD_bbbbbbbbbbbbbbbbbbbb.jpg"
    first_new = "NEW_aaaaaaaaaaaaaaaaaaaa.jpg"
    second_new = "NEW_bbbbbbbbbbbbbbbbbbbb.jpg"
    (tmp_path / first_old).write_bytes(b"first")
    (tmp_path / second_old).write_bytes(b"second")
    record = _record(code="OLD", file_names=(first_old, second_old))
    original_rename = Path.rename

    def fail_second_rename(path, target):
        if path.name == second_old:
            raise OSError("rename failed")
        return original_rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_second_rename)

    with pytest.raises(OSError):
        asyncio.run(
            update_image_asset_service(
                str(record.id),
                code="NEW",
                storage_dir=tmp_path,
            )
        )

    assert (tmp_path / first_old).exists()
    assert (tmp_path / second_old).exists()
    assert not (tmp_path / first_new).exists()
    assert not (tmp_path / second_new).exists()


def test_update_code_does_not_rename_file_removed_in_same_request(
    tmp_path,
    monkeypatch,
):
    removed_name = "OLD_aaaaaaaaaaaaaaaaaaaa.jpg"
    kept_old_name = "OLD_bbbbbbbbbbbbbbbbbbbb.jpg"
    kept_new_name = "NEW_bbbbbbbbbbbbbbbbbbbb.jpg"
    new_name = "NEW_cccccccccccccccccccc.jpg"
    (tmp_path / removed_name).write_bytes(b"removed")
    (tmp_path / kept_old_name).write_bytes(b"kept")
    new_image = _stored_image(tmp_path, new_name)
    monkeypatch.setattr(
        service,
        "store_upload_batch",
        AsyncMock(return_value=[new_image]),
    )
    record = _record(code="OLD", file_names=(removed_name, kept_old_name))

    result = asyncio.run(
        update_image_asset_service(
            str(record.id),
            code="NEW",
            uploads=[object()],
            remove_image_file_names=[removed_name],
            storage_dir=tmp_path,
        )
    )

    assert result.url_images == [
        f"http://localhost:8000/rag-images/{kept_new_name}",
        new_image.public_url,
    ]
    assert not (tmp_path / removed_name).exists()
    assert not (tmp_path / kept_old_name).exists()
    assert (tmp_path / kept_new_name).exists()


def test_update_adds_new_image_and_removes_old_after_database_save(
    tmp_path,
    monkeypatch,
):
    first_name = "CODE_aaaaaaaaaaaaaaaaaaaa.jpg"
    second_name = "CODE_bbbbbbbbbbbbbbbbbbbb.jpg"
    new_name = "CODE_cccccccccccccccccccc.jpg"
    (tmp_path / first_name).write_bytes(b"first")
    (tmp_path / second_name).write_bytes(b"second")
    new_image = _stored_image(tmp_path, new_name)
    monkeypatch.setattr(
        service,
        "store_upload_batch",
        AsyncMock(return_value=[new_image]),
    )
    record = _record(file_names=(first_name, second_name))

    result = asyncio.run(
        update_image_asset_service(
            str(record.id),
            uploads=[object()],
            remove_image_file_names=[first_name, first_name],
            storage_dir=tmp_path,
        )
    )

    assert result.url_images == [
        f"http://localhost:8000/rag-images/{second_name}",
        new_image.public_url,
    ]
    assert not (tmp_path / first_name).exists()
    assert (tmp_path / second_name).exists()
    assert (tmp_path / new_name).exists()


def test_update_adds_multiple_images_in_order(tmp_path, monkeypatch):
    old_name = "CODE_aaaaaaaaaaaaaaaaaaaa.jpg"
    first_new_name = "CODE_bbbbbbbbbbbbbbbbbbbb.jpg"
    second_new_name = "CODE_cccccccccccccccccccc.jpg"
    (tmp_path / old_name).write_bytes(b"old")
    new_images = [
        _stored_image(tmp_path, first_new_name),
        _stored_image(tmp_path, second_new_name),
    ]
    monkeypatch.setattr(
        service,
        "store_upload_batch",
        AsyncMock(return_value=new_images),
    )
    record = _record(file_names=(old_name,))

    result = asyncio.run(
        update_image_asset_service(
            str(record.id),
            uploads=[object(), object()],
            storage_dir=tmp_path,
        )
    )

    assert result.url_images == [
        f"http://localhost:8000/rag-images/{old_name}",
        new_images[0].public_url,
        new_images[1].public_url,
    ]


def test_update_removes_multiple_images_and_keeps_remaining_order(tmp_path):
    first_name = "CODE_aaaaaaaaaaaaaaaaaaaa.jpg"
    second_name = "CODE_bbbbbbbbbbbbbbbbbbbb.jpg"
    third_name = "CODE_cccccccccccccccccccc.jpg"
    for file_name in (first_name, second_name, third_name):
        (tmp_path / file_name).write_bytes(file_name.encode())
    record = _record(file_names=(first_name, second_name, third_name))

    result = asyncio.run(
        update_image_asset_service(
            str(record.id),
            remove_image_file_names=[first_name, third_name],
            storage_dir=tmp_path,
        )
    )

    assert result.url_images == [
        f"http://localhost:8000/rag-images/{second_name}"
    ]
    assert not (tmp_path / first_name).exists()
    assert (tmp_path / second_name).exists()
    assert not (tmp_path / third_name).exists()


def test_update_database_error_removes_new_file_but_keeps_old_file(
    tmp_path,
    monkeypatch,
):
    old_name = "CODE_aaaaaaaaaaaaaaaaaaaa.jpg"
    new_name = "CODE_bbbbbbbbbbbbbbbbbbbb.jpg"
    (tmp_path / old_name).write_bytes(b"old")
    new_image = _stored_image(tmp_path, new_name)
    monkeypatch.setattr(
        service,
        "store_upload_batch",
        AsyncMock(return_value=[new_image]),
    )
    record = _record(file_names=(old_name,))
    record.save_error = RuntimeError("save failed")

    with pytest.raises(RuntimeError):
        asyncio.run(
            update_image_asset_service(
                str(record.id),
                uploads=[object()],
                storage_dir=tmp_path,
            )
        )

    assert (tmp_path / old_name).exists()
    assert not (tmp_path / new_name).exists()
    assert record.url_images == [f"http://localhost:8000/rag-images/{old_name}"]


def test_delete_service_deletes_record_and_all_existing_files(tmp_path):
    first_name = "CODE_aaaaaaaaaaaaaaaaaaaa.jpg"
    second_name = "CODE_bbbbbbbbbbbbbbbbbbbb.jpg"
    (tmp_path / first_name).write_bytes(b"first")
    record = _record(file_names=(first_name, second_name))

    asyncio.run(delete_image_asset_service(str(record.id), storage_dir=tmp_path))

    assert record.deleted is True
    assert _FakeImageAsset.records == []
    assert not (tmp_path / first_name).exists()

    with pytest.raises(ImageAssetProcessingError) as second_delete:
        asyncio.run(delete_image_asset_service(str(record.id), storage_dir=tmp_path))
    assert second_delete.value.status_code == 404


def test_cleanup_file_error_is_best_effort(monkeypatch, caplog):
    class _FailingPath:
        def unlink(self, missing_ok=False):
            del missing_ok
            raise OSError("permission denied")

    monkeypatch.setattr(
        service,
        "resolve_storage_file",
        lambda *args, **kwargs: _FailingPath(),
    )

    service._cleanup_file_names(["CODE_a.jpg"])

    assert "IMAGE_ASSET_IMAGE_DELETE_FAILED" in caplog.text


def test_update_succeeds_when_removed_file_cleanup_fails(monkeypatch, caplog):
    first_name = "CODE_aaaaaaaaaaaaaaaaaaaa.jpg"
    second_name = "CODE_bbbbbbbbbbbbbbbbbbbb.jpg"
    record = _record(file_names=(first_name, second_name))

    class _FailingPath:
        def unlink(self, missing_ok=False):
            del missing_ok
            raise OSError("permission denied")

    monkeypatch.setattr(
        service,
        "resolve_storage_file",
        lambda *args, **kwargs: _FailingPath(),
    )

    result = asyncio.run(
        update_image_asset_service(
            str(record.id),
            remove_image_file_names=[first_name],
        )
    )

    assert result.url_images == [
        f"http://localhost:8000/rag-images/{second_name}"
    ]
    assert "IMAGE_ASSET_IMAGE_DELETE_FAILED" in caplog.text


def test_delete_completes_when_file_cleanup_fails(monkeypatch, caplog):
    record = _record()

    class _FailingPath:
        def unlink(self, missing_ok=False):
            del missing_ok
            raise OSError("permission denied")

    monkeypatch.setattr(
        service,
        "resolve_storage_file",
        lambda *args, **kwargs: _FailingPath(),
    )

    asyncio.run(delete_image_asset_service(str(record.id)))

    assert record.deleted is True
    assert "IMAGE_ASSET_IMAGE_DELETE_FAILED" in caplog.text


def test_delete_rejects_invalid_id():
    with pytest.raises(ImageAssetProcessingError) as exc:
        asyncio.run(delete_image_asset_service("invalid-id"))

    assert exc.value.status_code == 400


def test_rename_rollback_failure_is_logged(monkeypatch, caplog):
    class _OldPath:
        def exists(self):
            return False

    class _NewPath:
        def exists(self):
            return True

        def rename(self, target):
            del target
            raise OSError("rollback failed")

    renamed = service.RenamedImage(
        old_file_name="OLD_a.jpg",
        new_file_name="NEW_a.jpg",
        old_path=_OldPath(),
        new_path=_NewPath(),
    )

    service._rollback_renamed_images([renamed])

    assert "IMAGE_ASSET_RENAME_ROLLBACK_FAILED" in caplog.text
