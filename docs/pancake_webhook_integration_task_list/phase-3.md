# Task List Phase 3: Tích hợp với conversation/message hiện tại

## Mục tiêu

Phase 3 nối object Pancake đã normalize vào model `Conversation` và `Message` hiện có. Sau phase này, BE có thể nhận message Pancake, tìm hoặc tạo conversation theo `sender_id`, chống trùng bằng `message_mid`, lưu message khách và chuẩn bị dữ liệu cho bước gọi AI/reply.

Phase này tập trung vào persistence và idempotency. Việc gọi Pancake Public API nằm ở phase 4.

## Phạm vi thay đổi

- Get/create `Conversation` từ object normalize.
- Update thông tin channel/customer khi có dữ liệu mới.
- Check duplicate message bằng `Message.message_mid`.
- Lưu message khách với meta Pancake.
- Xử lý message admin/echo/page gửi ra nếu Pancake có tín hiệu phân biệt.
- Pause bot khi admin Pancake người thật tham gia hội thoại.
- Test database/service path với mock model hoặc pattern test hiện có.

## File dự kiến thay đổi

- `app/api/v1/pancake_webhook.py`
- `app/services/pancake_webhook_normalize_service.py`, nếu đã tách ở phase 2.
- [app/models/conversations.py](../../app/models/conversations.py), nếu cần index/field mới.
- [app/models/messages.py](../../app/models/messages.py), nếu cần index mới.
- `tests/test_pancake_webhook.py`

## Checklist

### 1. Get/create conversation

- [x] Tạo helper lấy hoặc tạo conversation từ object normalize.
- [x] Tìm conversation theo `Conversation.customer_id == sender_id`.
- [x] Nếu có nhiều conversation cùng customer, dùng behavior tương tự Facebook hiện tại, ưu tiên bản mới cập nhật gần nhất.
- [x] Khi tạo mới, set `channel` từ `page_name`, fallback `page_id`.
- [x] Khi tạo mới, set `customer_name` từ `sender_name`.
- [x] Khi tạo mới, set `customer_id` từ `sender_id`.
- [x] Khi tạo mới, giữ `is_active = true`.
- [x] Khi tạo mới, để `status` default theo model hiện tại.
- [x] Khi tìm thấy conversation, update `channel`/`customer_name` nếu có giá trị mới hợp lệ.
- [x] Khi conversation đang inactive, cân nhắc behavior hiện tại trước khi bật lại active.

Kết quả mong muốn:
  Pancake message được gắn vào conversation nội bộ ổn định, giống flow Facebook.

### 2. Duplicate guard

- [x] Check `message_mid` đã tồn tại trong collection `messages`.
- [x] Nếu trùng, trả skip reason `duplicate_message_mid` hoặc tương đương.
- [x] Nếu có cơ chế inflight giống Facebook, cân nhắc thêm set/lock cho Pancake để tránh double process song song.
- [x] Chỉ đánh dấu inflight sau khi payload hợp lệ.
- [x] Clear inflight khi xử lý xong hoặc khi enqueue thất bại.
- [x] Không gọi AI/reply khi duplicate.

Kết quả mong muốn:
  Cùng một Pancake message không tạo nhiều message và không reply nhiều lần.

### 3. Lưu message khách

- [x] Tạo `Message` với `conversation_id` nội bộ.
- [x] Set `message_mid` từ object normalize.
- [x] Set `role = "user"` cho message khách gửi vào.
- [x] Set `content` từ `text` đã normalize.
- [x] Set `created_at`/`updated_at` theo helper thời gian hiện có.
- [x] Lưu `meta.source = "pancake_webhook_ai_forward"` hoặc tên source đã chốt.
- [x] Lưu `meta.page_id`.
- [x] Lưu `meta.sender_id`.
- [x] Lưu `meta.platform`.
- [x] Lưu `meta.platform_sender_id`.
- [x] Lưu `meta.page_customer_id`.
- [x] Lưu `meta.pancake_conversation_id`.
- [x] Lưu `meta.timestamp`.
- [x] Lưu `meta.attachments`.
- [x] Lưu `meta.post_id`.
- [x] Không lưu token trong `meta`.

Kết quả mong muốn:
  Database có đủ dữ liệu để xem lại hội thoại và debug nguồn Pancake.

### 4. Xử lý echo/admin/page message

- [x] Xác định Pancake có field nào phân biệt message do page/admin gửi ra.
- [x] Nếu `data.message.from.id == page_id` và `admin_name == "Public API"`, coi là bot/API echo và bỏ qua.
- [x] Nếu `data.message.from.id == page_id` và `admin_name` khác `Public API`, coi là admin người thật.
- [x] Khi admin người thật gửi tin, tìm conversation bằng `data.conversation.customer_id` thay vì page id.
- [x] Nếu detect được page/admin message, không đưa vào AI như message khách.
- [x] Nếu cần lưu admin message, dùng `role = "staff"`.
- [x] Source meta admin nên khác source message khách.
- [x] Set `Conversation.bot_paused_at`, `bot_paused_until`, `bot_paused_reason`, `bot_paused_by` khi admin người thật tham gia.
- [x] Không tạo reply loop khi BE nhận lại chính message vừa gửi qua Pancake.
- [x] Nếu chưa có tín hiệu echo rõ ràng, document rủi ro và chỉ xử lý `INBOX` khách trong phase đầu.

Kết quả mong muốn:
  Pancake webhook không tự reply vào message do page/admin/bot gửi ra.

### 5. Chuẩn bị payload cho AI/rule

- [x] Chuẩn hóa input AI chỉ gồm text và context cần thiết.
- [x] Không gửi raw payload Pancake trực tiếp sang AI.
- [x] Giữ `conversation_id` nội bộ để lưu bot response ở phase sau.
- [x] Giữ `pancake_conversation_id` để phase 4 gửi reply.
- [x] Nếu text rỗng, skip AI với reason rõ ràng trong phase đầu.

Kết quả mong muốn:
  Dữ liệu đã sẵn sàng nối sang xử lý phản hồi mà không phụ thuộc raw Pancake.

### 6. Test persistence

- [x] Test tạo conversation mới từ message Pancake hợp lệ.
- [x] Test reuse conversation cũ theo `sender_id`.
- [x] Test update `customer_name` khi sender name mới có giá trị.
- [x] Test duplicate `message_mid` bị skip.
- [x] Test message user được insert đúng `role`, `content`, `message_mid`.
- [x] Test meta có đủ `page_id`, `sender_id`, `pancake_conversation_id`.
- [x] Test message thiếu text hoặc bị removed không tạo message user nếu phase đầu skip.
- [x] Test echo/admin message không gọi path user reply nếu có rule detect.
- [x] Test admin người thật lưu staff message và pause đúng conversation khách.
- [x] Test Public API echo không lưu staff message và không pause.

Kết quả mong muốn:
  Persistence path hoạt động ổn định trước khi bật gửi reply.

## Acceptance criteria

- [x] Pancake message tạo/reuse được `Conversation`.
- [x] `Conversation.customer_id` dùng `sender_id` normalize.
- [x] Duplicate `message_mid` không xử lý lần hai.
- [x] Message khách được lưu với `role = "user"`.
- [x] Message admin người thật được lưu với `role = "staff"` và không gọi AI.
- [x] Meta lưu đủ field Pancake cần để debug và gửi reply.
- [x] Không lưu token vào database.
- [x] Test persistence pass.
- [x] `pytest -q` pass.

## Ghi chú mở

- Nếu cần index `message_mid` riêng để duplicate check nhanh hơn, nên cân nhắc thêm trong model `Message`.
- Nếu nhiều page dùng chung customer id nền tảng, nên namespace `sender_id` trước khi chạy production.
