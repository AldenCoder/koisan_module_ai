# Task List Phase 3: Bổ sung API gửi reply comment

## Mục tiêu

Phase 3 bổ sung service gọi Pancake Public API để gửi reply công khai vào comment. Service này phải có contract riêng cho `reply_comment`, vì khác với `reply_inbox` ở field bắt buộc `message_id`.

Phase này chỉ xây API client và unit test. Việc nối vào flow webhook end-to-end nằm ở Phase 4.

Kết quả mong muốn:

- Có constant `PANCAKE_REPLY_COMMENT_ACTION`.
- Có helper build payload reply comment text-only.
- Có hàm `send_pancake_comment_reply`.
- Có helper build payload media reply comment.
- Có hàm `send_pancake_comment_content_ids`.
- Validation đủ các field bắt buộc trước khi gọi HTTP.
- Reuse token mapping, timeout, retry, backoff và classify lỗi hiện có.
- Không log token hoặc full URL chứa token.

## Đầu vào đã chốt

- Phase 1-2 đã đảm bảo có `page_id`, `pancake_conversation_id`, `comment_message_id` và reply text.
- Text và media được gửi bằng hai request tách biệt.
- Token vẫn lấy từ `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID`.
- Query token vẫn là `page_access_token`.

## Ngoài phạm vi Phase 3

- Chưa nối `send_pancake_comment_reply` vào `_process_normalized_message`.
- Chưa triển khai mentions.
- Chưa thêm resolve conversation API.
- Chưa đổi `send_pancake_reply` hiện có cho inbox.

## File chính dự kiến sửa

- [app/services/pancake_message_service.py](../../app/services/pancake_message_service.py)
- [tests/test_pancake_message_service.py](../../tests/test_pancake_message_service.py)
- [app/core/config.py](../../app/core/config.py), nếu bổ sung config sender/mentions sau này.

## Checklist

### 1. Thêm constant và payload builder

- [x] Thêm `PANCAKE_REPLY_COMMENT_ACTION = "reply_comment"`.
- [x] Thêm helper build payload reply comment.
- [x] Payload luôn có `action`.
- [x] Payload luôn có `message_id`.
- [x] Payload luôn có `message`.
- [x] Payload text không trộn thêm `content_ids`.
- [x] Không thêm `mentions` trong phase đầu nếu chưa test contract.
- [x] Không thêm `sender_id` mặc định nếu business chưa chốt.

Kết quả mong muốn:
  Body gửi Pancake đúng contract text-only và không nhập nhằng với inbox.

### 2. Payload và service gửi media comment

- [x] Thêm helper build payload media reply comment.
- [x] Payload có `action = reply_comment`.
- [x] Payload có `message_id = comment_message_id`.
- [x] Payload có `content_ids`.
- [x] Payload media không gửi kèm `message`.
- [x] Thêm `send_pancake_comment_content_ids`.
- [x] Validate `page_id`, `conversation_id`, `comment_message_id`, `content_ids`.
- [x] Reuse token mapping, timeout, retry, backoff và classify lỗi.
- [x] Không reuse payload inbox vì payload inbox thiếu `message_id`.

Kết quả mong muốn:
  Media đã upload vào Pancake có thể được reply vào đúng comment gốc bằng request riêng.

### 3. Thêm hàm gửi reply comment

- [x] Thêm `send_pancake_comment_reply`.
- [x] Nhận `page_id`.
- [x] Nhận `conversation_id`.
- [x] Nhận `comment_message_id`.
- [x] Nhận `message`.
- [x] Nhận optional timeout/retry giống service hiện có.
- [x] Dùng endpoint messages hiện có theo page và conversation.
- [x] Gọi `_post_pancake_reply_payload` hoặc helper thấp hơn phù hợp sau khi build payload.

Kết quả mong muốn:
  Có wrapper riêng cho comment reply, dễ đọc và dễ test.

### 4. Validation đầu vào

- [x] Thiếu `page_id` return `missing_page_id`.
- [x] Thiếu `conversation_id` return `missing_pancake_conversation_id`.
- [x] Thiếu `comment_message_id` return `missing_pancake_comment_message_id`.
- [x] Thiếu `message` return `missing_reply_message`.
- [x] Trim whitespace các string đầu vào.
- [x] Không gọi HTTP khi validation fail.
- [x] Không lookup token khi thiếu field cơ bản.

Kết quả mong muốn:
  Không có request Pancake sai contract từ dữ liệu thiếu.

### 5. Token, retry và lỗi HTTP

- [x] Lookup token bằng `_get_pancake_page_access_token_for_page`.
- [x] Thiếu token return `missing_pancake_page_access_token_for_page`.
- [x] Invalid token mapping return reason hiện có.
- [x] Reuse timeout từ `pancake_api_timeout_seconds`.
- [x] Reuse retry attempts từ `pancake_api_retry_attempts`.
- [x] Reuse backoff từ `pancake_api_retry_backoff_seconds`.
- [x] Không retry lỗi non-retryable 400/401/403/404.
- [x] Retry lỗi request tạm thời theo pattern hiện có.

Kết quả mong muốn:
  Behavior gửi comment nhất quán với các Pancake API client hiện tại.

### 6. Logging an toàn

- [x] Log send ok với `page_id`, `conversation_id`, status code và payload kind.
- [x] Log send failed với reason và response preview.
- [x] Log exception với attempt number.
- [x] Không log `page_access_token`.
- [x] Không log full URL có query token.
- [x] Không log full message nếu quá dài.

Kết quả mong muốn:
  Có đủ log debug mà không lộ token hoặc dữ liệu nhạy cảm.

### 7. Unit test service

- [x] Test build payload text-only đúng `action`, `message_id`, `message`.
- [x] Test thiếu `page_id` không gọi HTTP.
- [x] Test thiếu `conversation_id` không gọi HTTP.
- [x] Test thiếu `comment_message_id` không gọi HTTP.
- [x] Test thiếu `message` không gọi HTTP.
- [x] Test thiếu token theo page return reason đúng.
- [x] Test HTTP success return `ok = True`.
- [x] Test HTTP 400 return `pancake_payload_error` và non-retryable.
- [x] Test HTTP 401/403 return `pancake_auth_error`.
- [x] Test HTTP 404 return `pancake_conversation_not_found`.
- [x] Test request exception retry theo config.
- [x] Test build payload media đúng `action`, `message_id`, `content_ids`.
- [x] Test media thiếu field bắt buộc không lookup token/gọi HTTP.
- [x] Test media success gửi đúng payload và token theo page.

Kết quả mong muốn:
  Service được cover bằng mock HTTP, không gọi Pancake thật.

## Acceptance criteria

- [x] `send_pancake_comment_reply` có unit test happy path.
- [x] `send_pancake_comment_content_ids` có unit test happy path.
- [x] Validation thiếu dữ liệu bắt buộc có unit test.
- [x] Token mapping theo `page_id` có unit test.
- [x] Lỗi HTTP non-retryable có unit test.
- [x] Không thay đổi behavior `send_pancake_reply` cho inbox.
- [x] Không có test nào gọi external service thật.

## Ghi chú mở

- Nếu sau này cần `sender_id`, nên thêm tham số optional và test permission theo page.
- Nếu sau này cần mentions, cần test offset/length với Unicode tiếng Việt trước khi bật.
- Media phải tiếp tục gửi bằng helper riêng cho comment vì `message_id` là bắt buộc.
