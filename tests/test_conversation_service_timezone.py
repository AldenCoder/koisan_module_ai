import asyncio
from datetime import datetime, timedelta

from app.services import conversation_service as cs


class _FakeAggregateCursor:
    def __init__(self, rows):
        self._rows = rows

    async def to_list(self):
        return self._rows


class _FakeDoc:
    def __init__(self, *, created_at, updated_at):
        self.id = "doc-1"
        self.created_at = created_at
        self.updated_at = updated_at


def test_to_vn_aware_datetime_converts_naive_utc_to_utc_plus_7():
    naive_utc = datetime(2026, 4, 1, 4, 0, 0)
    converted = cs._to_vn_aware_datetime(naive_utc)

    assert converted is not None
    assert converted.utcoffset() == timedelta(hours=7)
    assert converted.hour == 11


def test_serialize_base_document_converts_datetime_to_vn_timezone():
    naive_utc = datetime(2026, 4, 1, 4, 13, 43)
    doc = _FakeDoc(created_at=naive_utc, updated_at=naive_utc)

    data = cs._serialize_base_document(doc)

    assert data["created_at"].utcoffset() == timedelta(hours=7)
    assert data["updated_at"].utcoffset() == timedelta(hours=7)
    assert data["created_at"].hour == 11
    assert data["updated_at"].hour == 11


def test_list_conversations_service_returns_vn_timezone_datetimes(monkeypatch):
    naive_utc = datetime(2026, 4, 1, 4, 13, 43)
    aggregate_rows = [
        {
            "items": [
                {
                    "_id": "conv-1",
                    "channel": "facebook",
                    "customer_name": "Nguyen Van A",
                    "customer_id": "fb_123",
                    "pancake_info_url": "https://pancake.vn/970198996185881?c_id=970198996185881_1",
                    "is_active": True,
                    "status": "new",
                    "summaries": None,
                    "created_at": naive_utc,
                    "updated_at": naive_utc,
                    "message_count": 2,
                }
            ],
            "total": [{"count": 1}],
        }
    ]

    monkeypatch.setattr(
        cs.Conversation,
        "aggregate",
        lambda pipeline: _FakeAggregateCursor(aggregate_rows),
    )

    result = asyncio.run(cs.list_conversations_service(page=1, size=10))

    item = result["items"][0]
    assert item["created_at"].utcoffset() == timedelta(hours=7)
    assert item["updated_at"].utcoffset() == timedelta(hours=7)
    assert item["pancake_info_url"] == (
        "https://pancake.vn/970198996185881?c_id=970198996185881_1"
    )
