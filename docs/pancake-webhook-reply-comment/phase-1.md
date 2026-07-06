# Task List Phase 1: Nhận webhook comment/post

## Mục tiêu

Phase 1 xác nhận contract webhook comment/post thực tế từ Pancake trước khi backend triển khai xử lý tự động. Mục tiêu là biết chắc webhook nào đại diện cho comment của khách, field nào là conversation Pancake, field nào là comment message id, và `data.post` đang mang ngữ cảnh bài viết ra sao.

Phase này ưu tiên quan sát và chốt dữ liệu. Chưa gửi reply comment, chưa gọi AI tự động cho comment nếu chưa đủ contract, và chưa thay đổi behavior production của flow `INBOX`.

Kết quả mong muốn:

- Có mẫu webhook comment thật từ Pancake trên page test.
- Chốt được webhook comment dùng `event_type = messaging`, `event_type = post`, hay cả hai.
- Xác định đúng `page_id`, `pancake_conversation_id`, `comment_message_id`, customer identity và `post_id`.
- Biết rõ trường hợp nào đủ dữ liệu để xử lý tiếp, trường hợp nào chỉ log/ignore.
- Có danh sách reason an toàn khi payload thiếu dữ liệu bắt buộc.

## Đầu vào đã chốt

- `data.post.id` là ID bài viết nguồn, không phải ID comment.
- `reply_comment` chỉ an toàn khi có đủ `page_id`, `pancake_conversation_id` và `comment_message_id`.
- Không dùng `post_id` thay cho `comment_message_id`.
- Không fallback sang `reply_inbox` cho comment.
- Phase đầu chỉ hỗ trợ text comment; media/mentions xử lý sau khi có payload thật.

## Ngoài phạm vi Phase 1

- Chưa sửa logic gửi Pancake API.
- Chưa thêm `send_pancake_comment_reply`.
- Chưa bật auto reply comment.
- Chưa xử lý media comment.
- Chưa resolve conversation bằng API phụ nếu webhook thiếu `conversation_id`.
- Chưa thay đổi flow auto consult hiện có.

## File chính dự kiến sửa

- [docs/pancake-webhook-reply-comment.md](../pancake-webhook-reply-comment.md)
- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py), nếu cần bổ sung log rút gọn.
- [app/services/pancake_webhook_normalize_service.py](../../app/services/pancake_webhook_normalize_service.py), nếu cần chuẩn bị helper inspect payload.
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py), nếu thêm fixture payload đã xác nhận.

## Tiến độ cập nhật

- Đã implement lớp nhận diện an toàn cho payload có `data.message.type = COMMENT`.
- Đã giữ `data.post.id` là `post_id`, không dùng làm `comment_message_id`.
- Đã thêm log/normalized public detail cho `comment_message_id`, `post_type`, `post_message_*` và `post_attachment_count`.
- Đã xác nhận `data.post.message` là nguồn caption dùng để bóc mã sản phẩm cho comment khách.
- Đã bổ sung normalized metadata `post_product_codes`, `post_product_code_count` và `comment_ai_message_augmented`.
- Log thực tế đã xác nhận webhook `post` thuần chỉ nên ignore, còn webhook `messaging` + `COMMENT` có đủ dữ liệu để đi tiếp sang AI.
- Log thực tế đã xác nhận `pancake_conversation_id = data.conversation.id` và `comment_message_id = data.message.id` với comment khách.
- Chưa implement gửi `reply_comment`; phần gửi API thuộc Phase 3-4.

## Checklist

### 1. Thu thập webhook comment thật

- [x] Cấu hình Pancake gửi webhook từ page test về backend/staging.
- [x] Tạo comment text thường dưới bài viết thường.
- [ ] Tạo comment dưới bài viết có ảnh.
- [ ] Tạo comment dưới bài livestream nếu page có dùng livestream.
- [ ] Tạo comment dưới bài ads/dark post nếu business có dùng ads.
- [x] Ghi nhận raw payload rút gọn cho từng case.
- [x] Xác nhận backend trả HTTP 200 để Pancake không retry vô hạn.

Kết quả mong muốn:
  Có ít nhất một payload comment text đủ dữ liệu để làm fixture test.

### 2. Xác nhận event và message type

- [x] Xác nhận `event_type` thực tế của comment là `messaging`, `post`, hay giá trị khác.
- [x] Xác nhận vị trí của `data.message.type`.
- [x] Xác nhận giá trị type dùng cho comment có phải `COMMENT` không.
- [x] Xác nhận payload `post` thuần có chứa `data.message` không.
- [x] Xác nhận khi payload chỉ có `data.post` thì không đủ để reply comment.
- [x] Chốt rule nhận diện webhook comment đủ điều kiện xử lý.

Kết quả mong muốn:
  Backend có rule phân biệt comment thật với post update thuần.

### 3. Xác nhận các ID bắt buộc

- [x] Xác nhận `page_id` lấy từ root `page_id` hay fallback `data.message.page_id`.
- [x] Xác nhận `pancake_conversation_id` lấy từ `data.conversation.id` hay `data.message.conversation_id`.
- [x] Xác nhận `comment_message_id` lấy từ field nào.
- [x] Xác nhận `comment_message_id` có trùng `data.message.id` không.
- [x] Xác nhận `data.post.id` khác `comment_message_id`.
- [x] Xác nhận có thể dùng `message_mid` hiện tại làm duplicate key cho comment không.
- [x] Xác nhận ID có ổn định khi Pancake retry cùng webhook không.

Kết quả mong muốn:
  Có mapping chính xác cho 3 ID bắt buộc: page, conversation, comment.

### 4. Xác nhận customer identity

- [x] Xác nhận ID khách ưu tiên là `data.message.from.page_customer_id` nếu có.
- [x] Xác nhận fallback customer là `data.message.from.id` hoặc `data.conversation.from.id`.
- [x] Xác nhận comment do page/admin gửi có `from.id == page_id` hay tín hiệu khác.
- [x] Xác nhận payload có `admin_name`/`uid` cho admin comment không.
- [x] Xác nhận không dùng page id làm `sender_id` cho AI user.
- [x] Xác nhận `sender_name` lấy từ message sender hay conversation sender.

Kết quả mong muốn:
  Comment khách được map vào đúng `Conversation.customer_id`, không gom nhầm vào page.

### 5. Xác nhận dữ liệu post context

- [x] Xác nhận `data.post.id` là post ID.
- [x] Xác nhận `data.post.message` có caption bài viết không.
- [x] Xác nhận `data.post.attachments` có media bài viết không.
- [x] Xác nhận `data.post.type` có đủ để log/debug không.
- [x] Xác nhận comment text không nằm trong `data.post.message`.
- [x] Chốt bóc mã sản phẩm từ full `data.post.message`, không bóc từ preview đã truncate.
- [x] Chốt dùng cùng regex mã sản phẩm với flow auto consult ad post.
- [x] Chốt chỉ lưu metadata/preview post, không lưu full raw dài nếu không cần.

Kết quả mong muốn:
  `data.post` được dùng làm context/audit, không dùng thay comment object.

### 6. Chốt reason khi thiếu dữ liệu

- [x] Chốt reason khi thiếu `page_id`.
- [x] Chốt reason khi thiếu `pancake_conversation_id`.
- [x] Chốt reason khi thiếu `comment_message_id`.
- [x] Chốt reason khi thiếu `sender_id`.
- [x] Chốt reason khi thiếu text comment.
- [x] Chốt reason cho post event thuần chỉ có `data.post`.
- [x] Chốt log field tối thiểu cho từng reason.

Kết quả mong muốn:
  Payload không đủ dữ liệu được ignore an toàn và dễ debug.

## Acceptance criteria

- [x] Có payload comment thật đã được xác nhận và lưu thành fixture hoặc mô tả field rõ ràng.
- [x] Team chốt được field chính xác của `pancake_conversation_id`.
- [x] Team chốt được field chính xác của `comment_message_id`.
- [x] Team xác nhận `data.post.id` không phải comment ID.
- [x] Team chốt được rule payload đủ dữ liệu để qua Phase 2.
- [x] Không có code gửi reply comment trong Phase 1.

## Ghi chú mở

- Nếu webhook thật không có `pancake_conversation_id`, cần mở phase riêng để resolve conversation từ Pancake API trước khi gửi reply.
- Nếu webhook thật không có comment message id ổn định, không nên triển khai auto reply comment cho đến khi Pancake xác nhận contract.
- Nên giữ raw payload test ở môi trường nội bộ, tránh commit dữ liệu khách thật vào repo.
