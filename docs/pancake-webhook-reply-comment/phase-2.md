# Task List Phase 2: Normalize và xử lý webhook comment/post

## Mục tiêu

Phase 2 triển khai lớp normalize và xử lý webhook comment/post sau khi Phase 1 đã chốt contract dữ liệu. Backend phải nhận diện được `customer_comment`, lưu đúng user message, gọi AI bằng text comment hợp lệ, nhưng chỉ chuyển sang gửi reply khi đã có đủ dữ liệu cho Phase 3-4.

Kết quả mong muốn:

- `normalize_pancake_payload` hiểu được comment payload mà không làm lệch flow `INBOX`.
- Có field riêng `comment_message_id`.
- Có metadata post an toàn để audit/debug.
- Bóc được mã sản phẩm từ caption bài viết và làm giàu payload gửi AI khi có mã.
- Có actor `customer_comment` trong classify.
- Comment khách đi qua duplicate guard, dangerous keyword guard và admin pause.
- Comment thiếu dữ liệu bắt buộc bị ignore với reason rõ ràng.

## Đầu vào đã chốt

- Phase 1 đã xác định field cho `page_id`, `pancake_conversation_id`, `comment_message_id`, `sender_id` và comment text.
- `data.post` chỉ là context bài viết.
- Auto consult `ad_card` và `page_comment_reply_notice` phải giữ nguyên thứ tự ưu tiên hiện có.
- `INBOX` hiện tại không được regression.

## Ngoài phạm vi Phase 2

- Chưa thêm API gửi `reply_comment`.
- Chưa gửi comment reply qua Pancake.
- Chưa xử lý media/mentions.
- Chưa resolve conversation khi webhook thiếu `pancake_conversation_id`.
- Chưa đổi flow gửi Drive image.

## File chính dự kiến sửa

- [app/services/pancake_webhook_normalize_service.py](../../app/services/pancake_webhook_normalize_service.py)
- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)
- `tests/test_pancake_comment_reply_service.py`, nếu tách helper parse comment riêng.

## Checklist

### 1. Mở rộng normalize payload

- [x] Giữ nguyên normalize hiện tại cho `INBOX`.
- [x] Thêm nhận diện payload có `message_type = COMMENT`.
- [x] Cho phép payload comment từ `event_type = messaging` nếu Phase 1 xác nhận.
- [ ] Cho phép log/ignore payload `event_type = post` thuần nếu thiếu message comment.
- [x] Ưu tiên text từ `original_message`, fallback strip HTML từ `message`.
- [x] Giữ `message_mid` làm duplicate id.
- [x] Không làm đổi cách detect page echo hiện có cho `INBOX`.

Kết quả mong muốn:
  Normalize comment đủ field nhưng không phá flow inbox đang chạy.

### 2. Bổ sung field comment/post

- [x] Bổ sung `comment_message_id` từ field đã chốt ở Phase 1.
- [x] Bổ sung `post_id` từ `data.post.id`.
- [x] Bổ sung `post_type` nếu có.
- [x] Bổ sung `post_message_present`.
- [x] Bổ sung `post_message_length`.
- [x] Bổ sung `post_message_preview` nếu cần audit, có truncate.
- [x] Bổ sung `post_attachments` hoặc `post_attachment_count` theo hướng an toàn.
- [x] Bóc `post_product_codes` từ full `data.post.message`.
- [x] Dùng `pancake_auto_consult_product_code_regex` để đồng nhất với ad post.
- [x] Bổ sung `post_product_code_count`.
- [x] Đảm bảo `post_id` không overwrite `comment_message_id`.

Kết quả mong muốn:
  Metadata đủ debug bài viết nguồn nhưng không nhầm ID comment.

### 3. Validation và reason

- [x] Return `missing_page_id` khi thiếu page.
- [x] Return `missing_pancake_conversation_id` khi thiếu conversation.
- [x] Return `missing_pancake_comment_message_id` khi thiếu comment message id.
- [x] Return `missing_sender_id` khi không xác định được khách.
- [x] Return `missing_message_content` khi comment không có text/attachment hợp lệ.
- [ ] Return reason riêng cho post event thuần nếu cần, ví dụ `missing_comment_message_id`.
- [x] Log normalized detail không chứa token hoặc raw quá dài.

Kết quả mong muốn:
  Payload lỗi không lọt vào AI/send và có reason đủ rõ để theo dõi.

### 4. Thêm actor `customer_comment`

- [x] Thêm constant/message kind `customer_comment`.
- [x] Classify `ad_card` trước `customer_comment`.
- [x] Classify `page_comment_reply_notice` trước `customer_comment`.
- [x] Classify `customer_comment` trước `customer_message`.
- [x] Điều kiện customer comment phải là sender không phải page.
- [x] Điều kiện customer comment phải có `message_type = COMMENT`.
- [x] Page/admin/automation comment không được classify thành `customer_comment`.

Kết quả mong muốn:
  Backend phân biệt comment khách với inbox khách và echo/page automation.

### 5. Xử lý customer comment trong webhook

- [x] Cho `_process_normalized_message` đi tiếp với `message_kind = customer_comment`.
- [x] Không áp rule `unsupported_message_type` cho `COMMENT` hợp lệ.
- [x] Check dangerous keyword trước khi gọi AI.
- [x] Check duplicate bằng `message_mid`.
- [x] Mark inflight để tránh xử lý song song cùng comment.
- [x] Lấy hoặc tạo conversation nội bộ theo `sender_id`.
- [x] Resume pause nếu pause đã hết hạn.
- [x] Lưu user message comment với `role = user`.
- [x] Nếu bot đang pause, dừng trước khi gọi AI.
- [x] Nếu text rỗng, dừng trước khi gọi AI.
- [x] Nếu post có mã, tạo AI message dạng `{comment}, tư vấn mã sản phẩm {product_codes_csv}, và gửi ảnh lookbook`.
- [x] Nếu post không có mã, gọi AI bằng nguyên text comment.
- [x] Không overwrite `normalized.text`; user message vẫn lưu comment gốc.
- [x] Log `PANCAKE_COMMENT_AI_MESSAGE_PREPARED` với `post_id`, `product_code_count` và `augmented`.

Kết quả mong muốn:
  Comment khách đi qua cùng guard an toàn như inbox, nhưng giữ metadata comment riêng.

### 6. Lưu metadata user message

- [x] Set `meta.source = pancake_webhook_comment`.
- [x] Lưu `page_id`.
- [x] Lưu `sender_id`.
- [x] Lưu `platform_sender_id`.
- [x] Lưu `page_customer_id`.
- [x] Lưu `pancake_conversation_id`.
- [x] Lưu `message_type = COMMENT`.
- [x] Lưu `comment_message_id`.
- [x] Lưu `post_id` nếu có.
- [x] Lưu post metadata dạng preview/count.
- [x] Lưu `post_product_codes`.
- [x] Lưu `post_product_code_count`.
- [x] Lưu `comment_ai_message_augmented`.
- [x] Không lưu token.

Kết quả mong muốn:
  Lịch sử nội bộ đủ trace comment gốc và bài viết nguồn.

## Acceptance criteria

- [x] Unit test normalize comment happy path pass.
- [x] Unit test missing `comment_message_id` pass.
- [x] Unit test missing `pancake_conversation_id` pass.
- [x] Unit test `post_id` không bị dùng làm `comment_message_id` pass.
- [x] Unit test classify `customer_comment` pass.
- [x] Unit test page sender không classify thành `customer_comment` pass.
- [x] Unit test `_process_normalized_message` không trả `unsupported_message_type` cho comment hợp lệ.
- [x] Unit test comment có mã tạo đúng AI hook message.
- [x] Unit test comment không có mã chỉ gửi nguyên comment.
- [x] Unit test bóc mã từ full caption dù mã nằm ngoài preview log.
- [x] Existing Pancake inbox tests không regression.

## Ghi chú mở

- Nếu comment có attachment nhưng không có text, phase đầu nên lưu audit và không gọi AI trừ khi business chốt rule riêng.
- Nếu payload admin comment không đủ tín hiệu `admin_name`/`uid`, ưu tiên ignore hơn là pause nhầm hoặc auto reply nhầm.
- Nếu Phase 2 đã gọi AI nhưng Phase 3 chưa bật gửi API, cần return reason rõ để không hiểu nhầm là gửi thất bại.
