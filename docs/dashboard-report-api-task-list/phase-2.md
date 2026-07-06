# Task List Phase 2: Service aggregate dashboard report

## Mục tiêu

Phase 2 implement service aggregate dữ liệu từ `messages` và `conversations`.

Kết quả mong muốn:

- API JSON trả đúng summary.
- API JSON trả đúng dữ liệu biểu đồ theo ngày.
- API JSON trả đúng cảnh báo cần hỗ trợ và đơn hàng.

## File chính dự kiến sửa

- `app/services/dashboard_report_service.py`
- `tests/test_dashboard_report_service.py`

## Checklist

- [x] Parse `from_date` và `to_date`.
- [x] Chuẩn hóa date theo timezone Việt Nam.
- [x] Validate `from_date <= to_date`.
- [x] Validate range không vượt giới hạn.
- [x] Build filter theo `page_id`.
- [x] Build filter theo `thread_type`.
- [x] Build filter theo `role`.
- [x] Build filter theo `include_inactive`.
- [x] Aggregate list `page_id` đang có từ `conversations` và `messages`.
- [x] Aggregate `total_messages`.
- [x] Aggregate `text_messages`.
- [x] Aggregate `image_messages`.
- [x] Aggregate `user_messages`.
- [x] Aggregate `staff_messages`.
- [x] Aggregate `bot_messages`.
- [x] Aggregate `messages_by_day`.
- [x] Aggregate `total_conversations`.
- [x] Aggregate `conversation_status`.
- [x] Query `alerts.needs_support`.
- [x] Query `alerts.orders`.
- [x] Tính `message_count` cho alert item.
- [x] Không trả raw message history.

## Acceptance criteria

- [x] Service trả object report dùng được cho API JSON.
- [x] Report không có field `mixed`.
- [x] Message có `content` là URL ảnh được tính vào image và không tính vào text.
