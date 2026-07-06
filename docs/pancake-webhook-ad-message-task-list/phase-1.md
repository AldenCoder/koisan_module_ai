# Task List Phase 1: Fetch và parse Pancake source detail

## Mục tiêu

Phase 1 bổ sung khả năng hydrate source detail từ Pancake Conversation Messages API. BE dùng `page_id`, `pancake_conversation_id` và trigger metadata để lấy lại message/context nguồn, sau đó trích xuất description bài viết/quảng cáo.

Kết quả mong muốn:

- Có service GET conversation messages dùng token đúng theo `page_id`.
- Ad card lấy được ad detail và description từ `post_attachments`.
- Page comment reply notice lấy được `comment_id`, tìm được post/comment context và description bài viết.
- Các lỗi thiếu dữ liệu trả reason rõ ràng, không gọi AI.

## Đầu vào đã chốt

- Token lấy từ `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID`.
- Param token theo contract hiện tại là `page_access_token`.
- Không log token hoặc URL đầy đủ có query token.
- Chỉ support `INBOX` trong phase đầu.

## Ngoài phạm vi Phase 1

- Chưa bóc product code.
- Chưa tạo synthetic normalized message.
- Chưa gọi AI.
- Chưa gửi Pancake reply.

## File chính dự kiến sửa

- [app/services/pancake_message_service.py](../../app/services/pancake_message_service.py)
- `app/services/pancake_auto_consult_service.py`, nếu tách helper riêng.
- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [tests/test_pancake_message_service.py](../../tests/test_pancake_message_service.py)
- `tests/test_pancake_auto_consult_service.py`, nếu tách helper riêng.

## Checklist

### 1. Thêm GET Conversation Messages API

- [x] Thêm `fetch_pancake_conversation_messages(page_id, conversation_id, ...)`.
- [x] Lookup token bằng `_get_pancake_page_access_token_for_page`.
- [x] Gọi endpoint `GET /pages/{page_id}/conversations/{conversation_id}/messages`.
- [x] Truyền `page_access_token` qua query params.
- [x] Dùng timeout/retry/backoff giống service Pancake hiện có.
- [x] Map lỗi auth thành `pancake_auth_error`.
- [x] Map 404 thành `pancake_conversation_not_found`.
- [x] Không log token hoặc full URL.

Kết quả mong muốn:
  BE có service hydrate conversation messages an toàn và test được bằng mocked HTTP.

### 2. Parse ad card detail

- [x] Tìm message có `id == ad_message_mid`.
- [x] Nếu không tìm thấy, return `pancake_ad_message_not_found`.
- [x] Tìm attachment `type=ad_click`.
- [x] Nếu không có `ad_click`, return `pancake_ad_click_missing`.
- [x] Extract `ad_id` từ `attachments[].ad_id`.
- [x] Extract description đầu tiên khác rỗng từ `attachments[].post_attachments[].description`.
- [x] Match `post_id` từ `ad_clicks[]` theo `ad_id` nếu có.
- [x] Fallback match `post_id` từ `customers[].ad_clicks[]` nếu cần.
- [x] Nếu không có description, return `pancake_ad_description_missing`.

Kết quả mong muốn:
  Ad card có object source detail đủ `trigger_type`, `trigger_message_mid`, `description`, `ad_id`, `post_id`.

### 3. Parse page comment reply notice

- [x] Nhận diện notice bằng sender page, text/original text chứa `Bạn đang phản hồi bình luận`, `message_tags` có `comment_id=`, attachments rỗng, không admin/uid.
- [x] Extract `comment_id` từ link trong `message_tags`.
- [x] Nếu thiếu `comment_id`, return `pancake_comment_id_missing`.
- [x] Fetch conversation messages bằng `page_id` và `pancake_conversation_id`.
- [x] Tìm message notice theo `message_mid` nếu response có message tương ứng.
- [x] Tìm post/comment context match `comment_id`.
- [x] Ưu tiên context có link chứa `comment_id=`.
- [x] Ưu tiên context có `attachments[].comment.msg_id` hoặc metadata comment tương ứng nếu Pancake trả field này.
- [x] Extract description từ `post_attachments[].description`.
- [x] Fallback description từ `attachments[].name` hoặc `attachments[].description` nếu đó là caption/post content.
- [x] Không parse mã từ text notice `Bạn đang phản hồi bình luận...`.
- [x] Nếu không tìm được context, return `pancake_comment_post_context_missing`.
- [x] Nếu context không có description, return `pancake_comment_post_description_missing`.

Kết quả mong muốn:
  Comment notice có object source detail đủ `trigger_type`, `trigger_message_mid`, `comment_id`, `description`, `post_id` nếu có.

## Acceptance criteria

- [x] Service GET Pancake Conversation Messages API có unit test.
- [x] Ad card detail parser có unit test happy path và lỗi thiếu dữ liệu.
- [x] Page comment reply parser có unit test happy path và lỗi thiếu dữ liệu.
- [x] Không có test nào gọi Pancake thật.
- [x] Không log token trong lỗi hoặc response.

## Ghi chú mở

- Nếu payload Pancake thực tế của comment context khác assumption, helper parse nên giữ nhiều fallback có kiểm soát và log `reason` đủ rõ.
