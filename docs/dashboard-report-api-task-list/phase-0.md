# Task List Phase 0: Chốt giải pháp dashboard report

## Mục tiêu

Phase 0 chốt phạm vi MVP cho API báo cáo dashboard.

Kết quả mong muốn:

- Thống nhất số lượng API cần làm.
- Thống nhất metric trả cho FE.
- Thống nhất dữ liệu cảnh báo cần hỗ trợ và cảnh báo đơn hàng.
- Thống nhất export Excel dùng cùng service với API JSON.

## Đầu vào đã chốt

- FE tự thiết kế giao diện.
- BE chỉ cần cung cấp API data và API export Excel.
- API bắt buộc có `from_date` và `to_date`.
- Phase đầu không cần nhóm `mixed`.

## Ngoài phạm vi Phase 0

- Không implement code.
- Không build UI.
- Không thêm metric nâng cao ngoài MVP.

## Checklist

- [x] Chốt cần 3 API: list `page_id`, JSON report và Excel export.
- [x] Chốt API JSON là `GET /api/v1/dashboard/report`.
- [x] Chốt API export là `GET /api/v1/dashboard/report/export`.
- [x] Chốt `from_date` và `to_date` là required.
- [x] Chốt metric tổng tin nhắn.
- [x] Chốt metric tổng tin nhắn text.
- [x] Chốt metric tổng tin nhắn ảnh.
- [x] Chốt không cần `mixed`.
- [x] Chốt biểu đồ tin nhắn theo ngày.
- [x] Chốt cảnh báo cần hỗ trợ gồm `handover`, `apilimit`, bot đang pause.
- [x] Chốt cảnh báo đơn hàng gồm `order_pending` hoặc có `order_note`.
- [x] Chốt Excel export dùng cùng service với JSON report.

## Acceptance criteria

- [x] Proposal chính mô tả rõ 3 API.
- [x] Proposal chính mô tả rõ metric MVP.
- [x] Proposal chính có checklist implementation tổng hợp.
