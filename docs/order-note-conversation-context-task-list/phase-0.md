# Task List Phase 0: Chốt giải pháp order_note và conversation_id context

## Mục tiêu

Phase 0 chốt phạm vi, contract và ranh giới trách nhiệm cho task lưu `order_note` vào `conversations` và gửi `conversation_id` sang AI Agent.

Phase này chỉ dùng để thống nhất giải pháp. Chưa sửa code, chưa thêm schema, chưa thêm endpoint và chưa thêm test.

## Đầu vào đã chốt

- BE không tạo order thật trong phase này.
- `order_note` chỉ là ghi chú cảnh báo cho sale.
- Dữ liệu lưu trực tiếp trên document `Conversation`.
- API nhận đúng 2 field trong body: `conversation_id` và `order_note`.
- `conversation_id` là định danh duy nhất để chọn conversation cần update.
- Nếu `conversation_id` sai hoặc không tìm thấy, BE không update gì và ghi warning log.
- Khi có order note, conversation chuyển sang `order_pending`.
- Khi sale xử lý xong, conversation quay về `new` và clear `order_note`.
- AI nhận `conversation_id` trong context message để tự gọi API order note.

## Quyết định cần chốt

- Endpoint chính là `POST /api/v1/order-notes`.
- Request body không nhận thêm `channel`, `customer_id`, `message_id`, `order_id` hoặc field định danh khác.
- Không fallback tìm conversation bằng khách hàng, kênh, tên khách hoặc conversation mới nhất.
- Không xử lý duplicate trong phase này vì payload không có idempotency key.
- Mỗi request hợp lệ có `conversation_id` tìm thấy sẽ append một dòng vào `order_note`.
- Format note append là `{index}. [HH:mm] {order_note}`.
- `HH:mm` dùng timezone hiện tại của app qua `now_vn()`.
- Không thêm bảng `orders` hoặc `conversation_order_notes`.
- Không thêm `order_note_count` trong phase này.
- Context note có `conversation_id` nên gửi ở mỗi lượt message sang AI, không chỉ init một lần.

## Ngoài phạm vi Phase 0

- Không implement endpoint.
- Không sửa model/schema.
- Không sửa webhook.
- Không sửa instruction phía AI Agent.
- Không xử lý retry duplicate.
- Không build UI dashboard mới.
- Không migrate/backfill dữ liệu cũ.

## File tài liệu liên quan

- [docs/order-note-conversation-context.md](../order-note-conversation-context.md)
- [docs/order-note-conversation-context-task-list/phase-1.md](phase-1.md)
- [docs/order-note-conversation-context-task-list/phase-2.md](phase-2.md)
- [docs/order-note-conversation-context-task-list/phase-3.md](phase-3.md)
- [docs/order-note-conversation-context-task-list/phase-4.md](phase-4.md)
- [docs/order-note-conversation-context-task-list/phase-5.md](phase-5.md)
- [docs/order-note-conversation-context-task-list/phase-6.md](phase-6.md)

## Checklist

### 1. Chốt API contract

- [x] Xác nhận endpoint `POST /api/v1/order-notes`.
- [x] Xác nhận payload chỉ có `conversation_id`.
- [x] Xác nhận payload chỉ có `order_note`.
- [x] Xác nhận không thêm auth data vào body.
- [x] Xác nhận `conversation_id` rỗng trả lỗi validation.
- [x] Xác nhận `order_note` rỗng sau khi trim trả lỗi validation.

Kết quả mong muốn:
  API contract đủ nhỏ để AI Agent dễ gọi và BE không phải suy luận thêm.

### 2. Chốt rule chọn conversation

- [x] Chỉ dùng `conversation_id` để lookup `Conversation`.
- [x] Nếu `conversation_id` sai format, trả `400`.
- [x] Nếu không tìm thấy conversation, trả `404`.
- [x] Không append `order_note` khi lookup thất bại.
- [x] Không đổi `status` khi lookup thất bại.
- [x] Log warning khi `conversation_id` invalid hoặc not found.
- [x] Không fallback sang bất kỳ field nào khác.

Kết quả mong muốn:
  BE không update nhầm conversation khi AI gửi sai id.

### 3. Chốt lifecycle trạng thái

- [x] AI báo đơn thì set `status = "order_pending"`.
- [x] Sale xử lý xong thì set `status = "new"`.
- [x] Sale xử lý xong thì set `order_note = null`.
- [x] Khách đặt tiếp sau khi đã xử lý thì tạo lại note từ `1.`.
- [x] Không dùng status khác để biểu diễn flow order note đơn giản này.

Kết quả mong muốn:
  Trạng thái chỉ thể hiện việc sale có đang cần xử lý ghi chú đơn hàng hay không.

### 4. Chốt AI context

- [x] Gửi `conversation_id` sang AI sau khi BE đã tạo/lấy conversation.
- [x] Context note có format cố định, dễ parse bằng text.
- [x] Context note được gửi ở mỗi lượt message sang AI.
- [x] Init/bootstrap đọc `SKILL.md` hiện tại vẫn giữ nguyên.
- [x] Conversation cũ đã initialized vẫn nhận được `conversation_id` ở lượt mới.

Kết quả mong muốn:
  AI luôn có `conversation_id` hiện tại khi cần gọi API order note.

## Acceptance criteria

- [x] Team thống nhất API body chỉ có 2 field.
- [x] Team thống nhất không fallback nếu sai `conversation_id`.
- [x] Team thống nhất `order_pending -> new` sau khi sale xử lý xong.
- [x] Team thống nhất không chống duplicate trong phase này.
- [x] Team thống nhất gửi `conversation_id` vào mỗi lượt message sang AI.

## Ghi chú mở

- Nếu sau này cần chống duplicate, thêm `message_id` hoặc `request_id` bằng task riêng.
- Nếu sau này cần quản lý nhiều order thật, mở task riêng để tạo collection order thay vì mở rộng `order_note` text.
