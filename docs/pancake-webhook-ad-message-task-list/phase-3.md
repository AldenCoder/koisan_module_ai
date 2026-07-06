# Task List Phase 3: Tạo normalized message tổng hợp và lưu audit

## Mục tiêu

Phase 3 tạo synthetic normalized message để tái sử dụng flow AI/reply hiện tại mà không dùng `page_id` làm user AI. Message tổng hợp có `text` là prompt lookbook, `is_echo=false`, và metadata đủ để audit/idempotency.

Kết quả mong muốn:

- AI session dùng customer thật.
- User message tổng hợp được lưu với `meta.source=pancake_auto_consult`.
- Metadata phân biệt được trigger ad card và page comment reply notice.
- Không lẫn với customer message thật.

## Đầu vào đã chốt

- Source detail từ Phase 1.
- `product_codes` và prompt từ Phase 2.
- Customer identity ưu tiên `conversation_customer_id`, `page_customer_id`, rồi `conversation_sender_id` nếu khác page.

## Ngoài phạm vi Phase 3

- Chưa gọi AI.
- Chưa gửi Pancake reply.
- Chưa xử lý Drive image output.

## File chính dự kiến sửa

- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- `app/services/pancake_auto_consult_service.py`, nếu tách helper riêng.
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)
- `tests/test_pancake_auto_consult_service.py`, nếu tách helper riêng.

## Checklist

### 1. Resolve customer identity

- [x] Lấy customer id từ `conversation_customer_id` nếu có.
- [x] Fallback `page_customer_id` nếu có.
- [x] Fallback `conversation_sender_id` nếu khác `page_id`.
- [x] Nếu không resolve được customer id, return `pancake_auto_consult_customer_missing`.
- [x] Không dùng raw `sender_id` của trigger nếu raw sender là page.
- [x] Giữ `conversation_sender_name` làm sender name nếu có.

Kết quả mong muốn:
  Mỗi khách có AI session riêng, không gom toàn bộ trigger vào session page.

### 2. Tạo normalized tổng hợp

- [x] Set `source=pancake_auto_consult`.
- [x] Set `sender_id` bằng customer id thật.
- [x] Set `recipient_id=page_id`.
- [x] Set `message_mid=trigger_message_mid`.
- [x] Set `message_type=INBOX`.
- [x] Set `conversation_type=INBOX`.
- [x] Set `is_echo=false`.
- [x] Set `text` bằng prompt lookbook.
- [x] Giữ `page_id`, `pancake_conversation_id`, `platform`, `conversation_customer_id`, `conversation_sender_id`, `conversation_sender_name`.
- [x] Gắn `auto_consult.trigger_type`.
- [x] Gắn `auto_consult.trigger_message_mid`.
- [x] Gắn `auto_consult.product_codes` và `product_code_count`.
- [x] Gắn `ad_id`, `ad_message_mid`, `post_id` nếu là ad card.
- [x] Gắn `comment_id`, `post_id` nếu là page comment reply notice.

Kết quả mong muốn:
  Object tổng hợp có thể đi qua flow customer/AI nhưng vẫn audit được nguồn trigger.

### 3. Lưu user message tổng hợp

- [x] Lấy hoặc tạo `Conversation` nội bộ theo customer id thật.
- [x] Kiểm tra duplicate trước khi lưu.
- [x] Lưu role `user`.
- [x] Lưu content bằng prompt lookbook.
- [x] Lưu `message_mid=trigger_message_mid`.
- [x] Lưu `meta.source=pancake_auto_consult`.
- [x] Lưu `meta.trigger_type`.
- [x] Lưu `meta.trigger_message_mid`.
- [x] Lưu `meta.product_codes`, `product_code_count`.
- [x] Lưu `description_present`, `description_length`, optional `description_preview` đã truncate.
- [x] Không lưu token.
- [x] Không bắt buộc lưu raw full description.

Kết quả mong muốn:
  Có lịch sử nội bộ và idempotency mà không làm nhiễu customer message thật.

## Acceptance criteria

- [x] Test ad card synthetic normalized dùng customer id thật.
- [x] Test comment notice synthetic normalized dùng customer id thật.
- [x] Test không dùng `page_id` làm AI user.
- [x] Test user message lưu `meta.source=pancake_auto_consult`.
- [x] Test metadata ad/comment khác nhau đúng trigger.
- [x] Test thiếu customer id return reason rõ ràng.

## Ghi chú mở

- Nếu sau này cần hiển thị rõ “auto consult” trên UI nội bộ, metadata phase này là nguồn chính.
