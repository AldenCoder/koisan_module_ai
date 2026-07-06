# Task List Phase 0: Chốt giải pháp tích hợp Pancake Webhook

## Mục tiêu

Phase 0 chốt phạm vi tích hợp Pancake Webhook trước khi implement. Pancake được thêm như một webhook source mới, nhưng dữ liệu sau khi nhận phải được chuẩn hóa về object nội bộ tương tự object `latest` của Facebook webhook hiện tại để không làm lệch luồng lưu `Conversation`, lưu `Message`, chống trùng message và gửi phản hồi.

Phase này chỉ chốt giải pháp và contract nội bộ. Chưa sửa code, chưa thêm endpoint, chưa gọi Pancake Public API.

## Quyết định cần chốt

- Pancake là webhook source mới, không thay đổi flow Facebook hiện tại.
- Endpoint public đề xuất là `/api/v1/pancake/webhook`.
- Raw payload Pancake không đi thẳng vào AI/rule hoặc database.
- BE normalize payload Pancake về object nội bộ trước khi xử lý.
- Object nội bộ bám sát các field Facebook webhook đang dùng: `page_id`, `sender_id`, `sender_name`, `recipient_id`, `timestamp`, `message_mid`, `text`, `metadata`, `raw`.
- Pancake cần bổ sung thêm `pancake_conversation_id` để gửi reply qua Pancake Public API.
- `sender_id` nội bộ ưu tiên `page_customer_id`, fallback về id khách trên nền tảng gốc.
- `Conversation.customer_id` dùng `sender_id` đã normalize.
- Page/bot/admin Pancake được phân biệt bằng `data.message.from.id == page_id` và `data.message.from.admin_name`.
- `admin_name = "Public API"` là bot/API echo; admin người thật là `admin_name` khác `Public API`.
- Khi admin người thật nhắn, pause bot cho customer lấy từ `data.conversation.customer_id`, tương tự Facebook admin takeover.
- `Conversation.channel` ưu tiên tên page nếu mapping được, fallback `page_id`.
- `Message.message_mid` dùng id message phía Pancake để chống xử lý trùng.
- Attachment chỉ lưu metadata trong phase đầu, chưa bắt buộc upload/rehost/gửi media.

## Ngoài phạm vi Phase 0

- Chưa tạo route FastAPI.
- Chưa thêm config token Pancake.
- Chưa viết service normalize.
- Chưa lưu conversation/message.
- Chưa gọi AI/rule.
- Chưa gọi Pancake Public API.
- Chưa thêm test.

## File tài liệu liên quan

- [docs/pancake_webhook_integration.md](../pancake_webhook_integration.md)
- [docs/pancake_webhook_integration_task_list/phase-1.md](phase-1.md)
- [docs/pancake_webhook_integration_task_list/phase-2.md](phase-2.md)
- [docs/pancake_webhook_integration_task_list/phase-3.md](phase-3.md)
- [docs/pancake_webhook_integration_task_list/phase-4.md](phase-4.md)
- [docs/pancake_webhook_integration_task_list/phase-5.md](phase-5.md)
- [docs/pancake_webhook_integration_task_list/phase-6.md](phase-6.md)

## Checklist

### 1. Chốt contract webhook source

- [x] Xác nhận Pancake là source mới, không sửa source Facebook hiện tại.
- [x] Xác nhận endpoint dùng prefix API v1: `/api/v1/pancake/webhook`.
- [x] Xác nhận chỉ xử lý event message hợp lệ, không xử lý mọi event Pancake.
- [x] Xác nhận phase đầu ưu tiên message khách gửi vào, không tự động reply event echo/admin/page gửi ra.
- [x] Xác nhận Public API echo chỉ bỏ qua, không pause bot.
- [x] Xác nhận admin Pancake người thật sẽ lưu staff message và pause bot theo customer trong conversation.
- [x] Xác nhận raw payload chỉ dùng để normalize/log/debug có kiểm soát.

Kết quả mong muốn:
  Team thống nhất Pancake đi vào BE qua một endpoint riêng và không ảnh hưởng behavior Facebook hiện tại.

### 2. Chốt object nội bộ

- [x] Xác nhận object nội bộ có `page_id`.
- [x] Xác nhận object nội bộ có `sender_id`.
- [x] Xác nhận object nội bộ có `sender_name`.
- [x] Xác nhận object nội bộ có `recipient_id`, với Pancake có thể dùng `page_id`.
- [x] Xác nhận object nội bộ có `timestamp`.
- [x] Xác nhận object nội bộ có `message_mid`.
- [x] Xác nhận object nội bộ có `text`.
- [x] Xác nhận object nội bộ có `metadata`.
- [x] Xác nhận object nội bộ có `pancake_conversation_id`.
- [x] Xác nhận object nội bộ có `conversation_customer_id` và `message_from_admin_name` để xử lý admin takeover.
- [x] Xác nhận object nội bộ có `attachments` và `post_id` nếu payload có.

Kết quả mong muốn:
  Object Pancake đủ giống object Facebook để reuse tư duy get/create conversation, duplicate check, save message và reply.

### 3. Chốt khóa lưu conversation

- [x] Xác nhận `sender_id` ưu tiên `data.message.from.page_customer_id`.
- [x] Xác nhận fallback `sender_id` là `data.message.from.id` hoặc `data.conversation.from.id`.
- [x] Xác nhận nếu cần tránh đụng nhiều page, có thể namespace `sender_id` bằng `page_id`.
- [x] Xác nhận `Conversation.customer_id` lưu `sender_id` đã normalize.
- [x] Xác nhận `Conversation.customer_name` lấy từ `sender_name`.
- [x] Xác nhận `Conversation.channel` ưu tiên `page_name`, fallback `page_id`.

Kết quả mong muốn:
  BE không tạo trùng conversation không cần thiết và vẫn có đủ thông tin khách để hiển thị/debug.

### 4. Chốt ranh giới media và reply

- [x] Xác nhận phase đầu chỉ cần text reply.
- [x] Xác nhận attachment nhận từ Pancake được lưu trong `Message.meta`.
- [x] Xác nhận chưa bắt buộc gửi lại attachment/media qua Pancake trong phase đầu.
- [x] Xác nhận gửi reply cần `page_id`, `pancake_conversation_id`, action và text.
- [x] Xác nhận token Pancake phải nằm trong biến môi trường hoặc hệ thống cấu hình an toàn, không hard-code.

Kết quả mong muốn:
  Scope phase đầu đủ nhỏ để tích hợp an toàn, không bị kéo sang bài toán media.

## Acceptance criteria

- [x] Tài liệu chính đã mô tả Pancake như webhook source mới.
- [x] Team chốt object nội bộ tương tự Facebook `latest`.
- [x] Team chốt khóa `sender_id` dùng để lưu `Conversation.customer_id`.
- [x] Team chốt `pancake_conversation_id` phải lưu trong object/meta.
- [x] Team chốt phase đầu chưa xử lý upload/rehost attachment.

## Ghi chú mở

- Nếu production xử lý nhiều page, nên quyết định sớm cách mapping `page_id` sang token và tên channel.
- Nếu sau này cần xác thực webhook riêng, nên mở task riêng thay vì đưa vào scope phase đầu.
