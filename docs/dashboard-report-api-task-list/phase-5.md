# Task List Phase 5: Test dashboard report

## Mục tiêu

Phase 5 bổ sung test cho API JSON, service aggregate và export Excel.

Kết quả mong muốn:

- Các behavior chính có test.
- `pytest -q` pass.
- Không chạy `pre-commit` theo guideline repo.

## File chính dự kiến sửa

- `tests/test_dashboard_report_service.py`
- `tests/test_dashboard_reports_api.py`

## Checklist

- [x] Test thiếu `from_date`.
- [x] Test thiếu `to_date`.
- [x] Test API list `page_id`.
- [x] Test `from_date > to_date`.
- [x] Test date range quá dài.
- [x] Test tổng message theo range.
- [x] Test message ngoài range không bị tính.
- [x] Test `messages_by_day` group đúng ngày theo timezone Việt Nam.
- [x] Test đếm `text_messages`.
- [x] Test đếm `image_messages`.
- [x] Test URL ảnh trong `content` được tính vào image và không tính vào text.
- [x] Test filter `page_id`.
- [x] Test filter `thread_type`.
- [x] Test filter `role`.
- [x] Test cảnh báo `handover`.
- [x] Test cảnh báo `apilimit`.
- [x] Test cảnh báo bot đang pause.
- [x] Test cảnh báo `order_pending`.
- [x] Test cảnh báo conversation có `order_note`.
- [x] Test export Excel trả đúng content type.
- [x] Test export Excel có filename đúng.
- [x] Test workbook có đủ sheet.
- [x] Chạy `pytest -q`.

## Acceptance criteria

- [x] Service tests pass.
- [x] API tests pass.
- [x] Export Excel tests pass.
- [x] `pytest -q` pass.
