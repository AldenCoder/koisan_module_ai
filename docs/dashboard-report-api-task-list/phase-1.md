# Task List Phase 1: Schema và router dashboard report

## Mục tiêu

Phase 1 tạo schema và router FastAPI cho dashboard report.

Kết quả mong muốn:

- Có response schema ổn định cho FE.
- Có endpoint list `page_id` cho FE render filter.
- Có endpoint JSON report.
- Có endpoint export Excel.
- Router được include vào API v1.

## File chính dự kiến sửa

- `app/api/schemas/dashboard_report.py`
- `app/api/v1/dashboard_reports.py`
- `app/api/router_v1.py`
- `tests/test_dashboard_reports_api.py`

## Checklist

- [x] Tạo schema filter response.
- [x] Tạo schema summary response.
- [x] Tạo schema `messages_by_day`.
- [x] Tạo schema `conversation_status`.
- [x] Tạo schema alert item dùng cho `needs_support`.
- [x] Tạo schema alert item dùng cho `orders`.
- [x] Tạo `DashboardReportResponse`.
- [x] Tạo schema response list `page_id`.
- [x] Tạo router `app/api/v1/dashboard_reports.py`.
- [x] Thêm endpoint `GET /api/v1/dashboard/report/page-ids`.
- [x] Thêm endpoint `GET /api/v1/dashboard/report`.
- [x] Thêm endpoint `GET /api/v1/dashboard/report/export`.
- [x] Dùng permission `conversations:view`.
- [x] Include router trong `app/api/router_v1.py`.

## Acceptance criteria

- [x] FE có contract response rõ ràng để tích hợp.
- [x] API v1 expose đúng 3 endpoint dashboard.
- [x] Endpoint export trả `StreamingResponse` hoặc response tương đương cho file `.xlsx`.
