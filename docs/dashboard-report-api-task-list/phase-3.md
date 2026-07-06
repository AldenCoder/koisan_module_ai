# Task List Phase 3: Export Excel dashboard report

## Mục tiêu

Phase 3 implement export báo cáo dashboard ra Excel.

Kết quả mong muốn:

- Export dùng cùng service với API JSON.
- File `.xlsx` có đủ sheet cần cho business kiểm tra.
- Header download đúng để FE tải file.

## File chính dự kiến sửa

- `app/services/dashboard_report_service.py`
- `app/api/v1/dashboard_reports.py`
- `tests/test_dashboard_reports_api.py`

## Checklist

- [x] Tạo helper build workbook bằng `openpyxl`.
- [x] Sheet `Summary` có filter đã dùng.
- [x] Sheet `Summary` có tổng tin nhắn.
- [x] Sheet `Summary` có tổng tin nhắn text.
- [x] Sheet `Summary` có tổng tin nhắn ảnh.
- [x] Sheet `Summary` có tổng user/staff/bot.
- [x] Sheet `Summary` có tổng conversation theo status.
- [x] Sheet `Messages by day` có `date`, `total`, `text`, `image`, `user`, `staff`, `bot`.
- [x] Sheet `Needs support` có danh sách cảnh báo cần hỗ trợ.
- [x] Sheet `Orders` có danh sách cảnh báo đơn hàng.
- [x] Endpoint export trả content type `.xlsx`.
- [x] Filename có range ngày.
- [x] Không ghi raw Excel bytes ra log.

## Acceptance criteria

- [x] File Excel mở được bằng `openpyxl`.
- [x] Workbook có đủ sheet `Summary`, `Messages by day`, `Needs support`, `Orders`.
- [x] Số liệu export khớp API JSON cùng filter.
