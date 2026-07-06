# Task List Phase 4: Logging, lỗi và an toàn dữ liệu dashboard report

## Mục tiêu

Phase 4 bổ sung logging, xử lý lỗi và các ràng buộc an toàn dữ liệu cho dashboard report.

Kết quả mong muốn:

- Lỗi filter trả rõ ràng.
- Không log dữ liệu nhạy cảm.
- Empty state trả payload hợp lệ.

## File chính dự kiến sửa

- `app/services/dashboard_report_service.py`
- `app/api/v1/dashboard_reports.py`
- `tests/test_dashboard_report_service.py`
- `tests/test_dashboard_reports_api.py`

## Checklist

- [x] Log request dashboard report với metadata filter.
- [x] Log request export với metadata filter.
- [x] Log count tổng sau khi aggregate.
- [x] Không log full message content.
- [x] Không log full order note.
- [x] Không log raw Excel bytes.
- [x] Thiếu `from_date` hoặc `to_date` trả lỗi rõ ràng.
- [x] `from_date > to_date` trả `400`.
- [x] Date range quá dài trả `400`.
- [x] Không có dữ liệu vẫn trả summary toàn số `0`.
- [x] Không có dữ liệu vẫn trả list rỗng hợp lệ.
- [x] Export lỗi trả `500` và không tạo file tạm không cần thiết.

## Acceptance criteria

- [x] Các lỗi date/filter có test.
- [x] Không có raw content trong log từ flow report.
- [x] Empty state không làm FE crash.
