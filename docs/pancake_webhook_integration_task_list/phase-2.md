# Task List Phase 2: Normalize payload Pancake

## Mục tiêu

Phase 2 xây helper/service normalize raw payload Pancake về object nội bộ ổn định. Object này cần đủ giống object `latest` của Facebook webhook để các phase sau có thể lấy/tạo conversation, chống trùng message, lưu message và gửi reply mà không phụ thuộc vào cấu trúc raw Pancake.

Normalize chỉ chuyển đổi dữ liệu và validate field tối thiểu. Phase này chưa cần gọi AI, chưa lưu database và chưa gửi reply.

## Phạm vi thay đổi

- Helper lấy nested field an toàn.
- Helper strip HTML text khi cần.
- Helper detect platform từ `page_id` hoặc prefix id.
- Helper normalize payload Pancake.
- Object kết quả normalize.
- Unit test normalize với payload hợp lệ, thiếu field và biến thể text.

## File dự kiến thay đổi

Tùy cách đặt code:

- `app/services/pancake_webhook_normalize_service.py`
- `app/api/v1/pancake_webhook.py`
- `tests/test_pancake_webhook.py`

Nếu gom helper vào webhook trong phase đầu:

- `app/api/v1/pancake_webhook.py`
- `tests/test_pancake_webhook.py`

## Checklist

### 1. Thiết kế object normalize

- [x] Object normalize có `source = "pancake_webhook"`.
- [x] Object normalize có `page_id`.
- [x] Object normalize có `page_name` nếu mapping được, không thì cho phép `None`.
- [x] Object normalize có `sender_id`.
- [x] Object normalize có `sender_name`.
- [x] Object normalize có `recipient_id`, với Pancake fallback bằng `page_id`.
- [x] Object normalize có `timestamp`.
- [x] Object normalize có `message_mid`.
- [x] Object normalize có `message_type`.
- [x] Object normalize có `is_echo` hoặc thông tin tương đương để phase sau tránh reply loop.
- [x] Object normalize có `text`.
- [x] Object normalize có `metadata`.
- [x] Object normalize có `pancake_conversation_id`.
- [x] Object normalize có `platform`, `platform_sender_id`, `page_customer_id`.
- [x] Object normalize có `conversation_customer_id`, `conversation_sender_id`, `conversation_sender_name`.
- [x] Object normalize có `message_from_id`, `message_from_admin_name`, `message_from_uid`, `message_from_ai_generated`.
- [x] Object normalize có `attachments`, `post_id`, `raw`.

Kết quả mong muốn:
  Caller không cần đọc raw Pancake để biết các field xử lý chính.

### 2. Mapping field Pancake

- [x] Map `page_id` từ root `page_id`, fallback `data.message.page_id`.
- [x] Map `event_type` từ root `event_type`.
- [x] Map `pancake_conversation_id` từ `data.conversation.id`, fallback `data.message.conversation_id`.
- [x] Map `conversation_type` từ `data.conversation.type`, fallback `data.message.type`.
- [x] Map `message_mid` từ `data.message.id`.
- [x] Map `message_type` từ `data.message.type`.
- [x] Map `platform_sender_id` từ `data.message.from.id`, fallback `data.conversation.from.id`.
- [x] Map `page_customer_id` từ `data.message.from.page_customer_id`.
- [x] Map `conversation_customer_id` từ `data.conversation.customer_id`.
- [x] Map `conversation_sender_id` và `conversation_sender_name` từ `data.conversation.from`.
- [x] Map `message_from_admin_name`, `message_from_uid`, `message_from_ai_generated` từ `data.message.from`.
- [x] Map `sender_name` từ `data.message.from.name`, fallback `data.conversation.from.name`.
- [x] Map `timestamp` từ `data.message.inserted_at`.
- [x] Map `attachments` từ `data.message.attachments`, default list rỗng.
- [x] Map `post_id` từ `data.post.id` nếu có.

Kết quả mong muốn:
  Các field quan trọng trong tài liệu chính được lấy đúng thứ tự ưu tiên.

### 3. Normalize text

- [x] Ưu tiên `data.message.original_message`.
- [x] Nếu không có `original_message`, fallback `data.message.message`.
- [x] Nếu fallback text có HTML, strip tag và unescape entity.
- [x] Trim text đầu/cuối.
- [x] Không đưa `None` vào AI hoặc `Message.content`.
- [x] Nếu text rỗng nhưng có attachment, quyết định reason xử lý rõ ràng cho phase đầu.

Kết quả mong muốn:
  Text đưa vào phase sau là text sạch, ổn định và không phụ thuộc raw HTML.

### 4. Chọn `sender_id` nội bộ

- [x] Ưu tiên `page_customer_id` làm `sender_id`.
- [x] Fallback `platform_sender_id` nếu thiếu `page_customer_id`.
- [x] Nếu cả hai thiếu, trả normalize invalid với reason rõ ràng.
- [x] Nếu cần namespace nhiều page, thiết kế helper tách riêng để dễ đổi.
- [x] Không dùng tên khách làm `sender_id`.

Kết quả mong muốn:
  `Conversation.customer_id` có khóa ổn định và không phụ thuộc display name.

### 5. Validate tối thiểu

- [x] Validate `event_type`.
- [x] Validate `page_id`.
- [x] Validate `pancake_conversation_id`.
- [x] Validate `message_mid`.
- [x] Validate `sender_id`.
- [x] Validate `message_type`.
- [x] Validate text hoặc attachment tùy scope phase đầu.
- [x] Trả object lỗi/reason thay vì raise exception không kiểm soát với payload thiếu field.

Kết quả mong muốn:
  Phase sau nhận được object hợp lệ hoặc reason skip rõ ràng.

### 6. Unit test normalize

- [x] Test payload `messaging` + `INBOX` đầy đủ normalize đúng field.
- [x] Test thiếu root `page_id` nhưng có `data.message.page_id`.
- [x] Test thiếu `page_customer_id` thì fallback `from.id`.
- [x] Test `original_message` được ưu tiên hơn `message`.
- [x] Test fallback `message` có HTML được strip.
- [x] Test thiếu `conversation_id` trả reason rõ ràng.
- [x] Test thiếu `message_mid` trả reason rõ ràng.
- [x] Test attachment được giữ trong object/meta.
- [x] Test post id được giữ nếu có.
- [x] Test payload page/admin map đúng `conversation_customer_id`, `message_from_admin_name`, `message_from_uid` và vẫn đánh dấu `is_echo`.
- [x] Test phân loại admin người thật khác `Public API`.

Kết quả mong muốn:
  Normalize có coverage đủ trước khi nối database/reply.

## Acceptance criteria

- [x] Có helper/service normalize payload Pancake.
- [x] Object normalize có đủ field tương đương Facebook `latest` và field riêng Pancake.
- [x] Field `sender_id` được chọn theo thứ tự ưu tiên đã chốt.
- [x] Text được normalize sạch.
- [x] Payload thiếu field bắt buộc có reason rõ ràng.
- [x] Unit test normalize pass.
- [x] `pytest -q` pass.

## Ghi chú mở

- Nếu Pancake trả thêm event type cho comment/private reply, nên giữ `message_type` và `conversation_type` trong object để phase 4 chọn action gửi reply đúng hơn.
- Nếu raw payload quá lớn, phase sau nên chỉ lưu raw rút gọn hoặc không lưu raw vào DB.
