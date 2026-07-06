# Tích hợp Pancake nhận webhook comment và tự động reply comment

## Mục tiêu

Tài liệu này mô tả định hướng triển khai để `BE` trong repo hiện tại nhận webhook comment từ Pancake, xử lý đúng dữ liệu comment/post, sau đó gửi phản hồi công khai bằng Pancake Public API với `action = reply_comment`.

Flow này phải triển khai theo thứ tự:

- Phần 1: nhận webhook và xử lý đúng webhook comment/post.
- Phần 2: gửi comment reply qua Pancake API.

Lý do tách như vậy: nếu chưa xác định đúng webhook, đúng `conversation_id`, đúng comment `message_id` và đúng khách hàng thì việc gửi reply comment rất dễ sai đích. Phần gửi API chỉ nên chạy sau khi phần nhận webhook đã chuẩn hóa dữ liệu đủ tin cậy.

Quy ước thuật ngữ:

- `BE` / `Backend`: repo hiện tại `koisan_module_ai`.
- `Pancake`: nền tảng gửi webhook và cung cấp Public API.
- `AI Agent` / `Brain`: service tạo câu trả lời đang được gọi qua flow Pancake/Facebook hiện có.
- `comment webhook`: webhook Pancake báo có comment của khách dưới bài viết.
- `post`: bài viết nguồn chứa comment.
- `reply_comment`: action Pancake dùng để trả lời công khai vào comment.
- `page_id`: ID page/kênh dùng trong URL Pancake API.
- `pancake_conversation_id`: ID conversation Pancake dùng trong URL API.
- `comment_message_id`: ID của comment cần reply, truyền vào body field `message_id`.
- `post_id`: ID bài viết nguồn, lấy từ `data.post.id`. Field này không phải ID comment.

## Luồng tổng thể

Khách comment vào bài viết trên page đã nối với Pancake.

Pancake gửi webhook về endpoint hiện tại của `BE`.

`BE` nhận raw payload, log rút gọn, xác định đây có phải webhook comment/post cần xử lý hay không.

Nếu webhook đủ dữ liệu comment hợp lệ, `BE` normalize payload thành object nội bộ, lưu comment của khách, gọi AI tạo câu trả lời, rồi gửi reply công khai bằng Pancake API.

Điểm bắt buộc:

- `data.post.id` chỉ là ID bài viết nguồn.
- `data.post.id` không được dùng làm `comment_message_id`.
- `reply_comment` cần `pancake_conversation_id` trong URL.
- `reply_comment` cần `comment_message_id` trong body.
- Không fallback sang `reply_inbox` khi message là comment.

## Hiện trạng hệ thống

Webhook Pancake hiện tại nằm ở:

- [app/api/v1/pancake_webhook.py](../app/api/v1/pancake_webhook.py)
- [app/services/pancake_webhook_normalize_service.py](../app/services/pancake_webhook_normalize_service.py)
- [app/services/pancake_message_service.py](../app/services/pancake_message_service.py)

Các điểm đã có sẵn:

- Endpoint nhận webhook Pancake.
- Normalize payload Pancake cho luồng inbox.
- Lấy `page_id`, `pancake_conversation_id`, `message_mid`, `message_type`, `sender_id`, `attachments`, `post_id`.
- Detect page echo/admin message.
- Lưu `Conversation` và `Message`.
- Duplicate guard theo `message_mid`.
- Dangerous keyword guard.
- Admin takeover pause.
- Gọi AI và gửi Pancake reply cho `INBOX`.
- Service Pancake đã có helper gửi message, upload content và gửi `content_ids` cho inbox.
- Token Pancake đang dùng mapping `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID`.

Các phần đã bổ sung cho reply comment:

- Normalize nhận diện và chuẩn hóa `COMMENT`, đồng thời tách `comment_message_id` khỏi `post_id`.
- `_process_normalized_message` xử lý `customer_comment` sau feature flag và các guard an toàn.
- `_resolve_pancake_reply_action` trả `reply_comment` cho comment.
- Service có payload riêng cho text và media `reply_comment`, đều truyền đúng `message_id`.
- Flow ảnh Drive reuse logic bóc link, chọn ảnh và cache/download hiện có; riêng comment upload từng file lên Pancake rồi gửi `content_id` vào đúng comment.

## Ranh giới trách nhiệm

### BE hiện tại

BE chịu trách nhiệm:

- Nhận webhook Pancake qua endpoint hiện có.
- Normalize payload comment/post thành object nội bộ ổn định.
- Phân biệt comment khách với page/admin/automation echo.
- Không xử lý tiếp khi thiếu `page_id`, `pancake_conversation_id` hoặc `comment_message_id`.
- Không dùng `data.post.id` thay cho comment message ID.
- Lấy hoặc tạo `Conversation` theo customer identity giống flow Pancake hiện tại.
- Lưu comment của khách vào `messages` với đủ metadata.
- Gọi AI bằng text comment đã normalize.
- Gửi reply công khai bằng `action = reply_comment`.
- Tách link Google Drive từ phản hồi AI, lấy ảnh lookbook và gửi ảnh vào đúng comment gốc.
- Lưu bot reply và Pancake send result vào database.
- Tôn trọng duplicate guard, dangerous keyword guard và admin pause hiện có.
- Log đủ thông tin debug, nhưng không log token hoặc URL chứa token.

### Pancake

Pancake chịu trách nhiệm:

- Gửi webhook khi có comment mới.
- Cung cấp `page_id`.
- Cung cấp `conversation_id` hoặc dữ liệu đủ để resolve conversation.
- Cung cấp ID comment cần reply.
- Cung cấp thông tin bài viết nguồn trong `data.post` nếu message type là `COMMENT`.
- Nhận API call `reply_comment`.

### AI Agent / Brain

AI Agent chịu trách nhiệm:

- Nhận text comment và context conversation do BE truyền.
- Trả về nội dung text phù hợp để reply cho khách.
- Không cần biết raw Pancake payload.
- Không tự gọi Pancake API.

### Ngoài phạm vi phase đầu

- Không tự suy luận comment ID từ `data.post.id`.
- Không tự resolve `conversation_id` bằng Get Conversations API nếu webhook thực tế chưa chứng minh đủ field để match an toàn.
- Không triển khai mentions trong phase đầu.
- Không thay đổi flow Facebook webhook.
- Không thay thế flow auto consult từ ad/comment notice đang có.

## Phần 1. Nhận webhook và xử lý webhook comment/post

Mục tiêu của phần 1 là làm cho backend hiểu đúng webhook comment/post trước khi có bất kỳ hành động gửi reply nào. Đây là lớp nền bắt buộc để tránh reply nhầm comment, nhầm bài viết hoặc nhầm khách hàng.

### Contract dữ liệu cần xác nhận

Webhook comment hợp lệ để xử lý tiếp cần có các nhóm dữ liệu sau:

| Nhóm dữ liệu | Bắt buộc | Mục đích |
|---|---:|---|
| `page_id` | Có | Xác định page và token gửi API sau này |
| `pancake_conversation_id` | Có | Xác định conversation Pancake chứa comment |
| `comment_message_id` | Có | Xác định comment cụ thể cần reply |
| `comment_text` | Có | Lưu message và gửi AI |
| `sender_id` | Có | Lấy/tạo conversation nội bộ |
| `sender_name` | Không | Cập nhật tên khách nếu có |
| `post_id` | Không | Lưu ngữ cảnh bài viết nguồn |
| `post_message` | Không | Ngữ cảnh bài viết, chỉ lưu preview/metadata nếu cần |
| `post_attachments` | Không | Ngữ cảnh media bài viết, chưa xử lý gửi ảnh ở phase đầu |

Nếu webhook chỉ có thông tin bài viết như `page_id` và `data.post.id`, backend chưa được xem là có đủ dữ liệu để reply comment.

### Cách hiểu `data.post`

`data.post` là thông tin bài viết nguồn của comment:

- `data.post.id` là ID bài viết.
- `data.post.message` là caption/nội dung bài viết.
- `data.post.attachments` là media của bài viết.
- `data.post.type` là loại bài viết như photo, video, livestream.

`data.post` không phải object comment. Vì vậy `data.post.id` không được dùng thay cho:

- `pancake_conversation_id`
- `comment_message_id`
- `sender_id`

### Normalize đề xuất

Nên mở rộng `normalize_pancake_payload` theo hướng tương thích ngược:

- Giữ nguyên behavior hiện tại cho `INBOX`.
- Cho phép nhận diện webhook comment khi payload có `message_type = COMMENT`.
- Cho phép log/ignore rõ ràng với `event_type = post` thuần chỉ có `data.post`.
- Bổ sung field riêng `comment_message_id` để tránh nhầm với `post_id`.
- Giữ `message_mid` là ID dùng cho duplicate guard, với comment có thể bằng `comment_message_id`.
- Bổ sung post metadata ở dạng an toàn, không lưu token và không log raw quá dài.
- Bóc mã sản phẩm trực tiếp từ full `data.post.message` bằng cùng regex đang dùng cho auto consult; không phụ thuộc vào `post_message_preview` đã truncate.
- Lưu danh sách mã đã bóc ở `post_product_codes` và số lượng ở `post_product_code_count`.
- Return reason rõ ràng khi thiếu field bắt buộc.

Normalized object sau phase này nên cung cấp đủ:

- `page_id`
- `sender_id`
- `sender_name`
- `pancake_conversation_id`
- `message_mid`
- `message_type`
- `comment_message_id`
- `text`
- `post_id`
- `post_type`
- `post_message_present`
- `post_message_length`
- `post_product_codes`
- `post_product_code_count`
- `attachments`
- `raw` để debug khi cần

### Phân loại actor đề xuất

Thứ tự classify trong Pancake webhook nên rõ như sau:

1. `ad_card`: trigger auto consult hiện có.
2. `page_comment_reply_notice`: trigger auto consult hiện có.
3. `customer_comment`: comment thật từ khách.
4. `customer_message`: inbox thật từ khách.
5. `human_admin_message`: page-side message/comment do admin thật gửi.
6. `page_echo_or_automation`: Public API, Botcake, POS, page echo/system còn lại.

Điều kiện nhận diện `customer_comment`:

- `message_type = COMMENT`.
- Sender không phải page.
- Không phải echo.
- Có nội dung comment.
- Có `pancake_conversation_id`.
- Có `comment_message_id`.

Nếu comment đến từ page/admin/automation, phase đầu không gọi AI tự động. Có thể ignore hoặc xử lý như staff message khi payload thực tế có tín hiệu admin đủ tin cậy.

### Xử lý webhook sau normalize

Khi `message_kind = customer_comment`, backend nên xử lý theo hướng:

- Kiểm tra dangerous keyword trên text comment.
- Check duplicate theo `message_mid`.
- Mark inflight theo `message_mid`.
- Lấy hoặc tạo `Conversation` nội bộ theo `sender_id`.
- Resume pause nếu pause đã hết hạn.
- Lưu user message với `role = user`.
- Nếu conversation đang pause, dừng trước khi gọi AI.
- Nếu text rỗng, dừng trước khi gọi AI.
- Bóc mã sản phẩm từ `data.post.message` bằng cùng regex cấu hình của auto consult.
- Nếu bài viết có mã sản phẩm và conversation chưa từng init AI trước webhook hiện tại, gọi AI bằng nội dung tổng hợp:

```text
{comment khách}, tư vấn mã sản phẩm {product_codes_csv}, và gửi ảnh lookbook
```

- Nếu bài viết có mã sản phẩm nhưng conversation đã `fb_ai_initialized = true` trước webhook hiện tại, xem đây là follow-up trong cùng thread. Backend chỉ gửi nguyên text comment của khách sang AI, không thêm ngữ cảnh mã sản phẩm và không gửi lại hook tư vấn/lookbook ban đầu:

```text
{comment khách}
```

- Giá trị `fb_ai_initialized` phải được đọc thành biến tạm trước khi gọi init Brain. Không dùng giá trị sau `_ensure_sender_initialized`, vì lần đầu init thành công sẽ đổi `fb_ai_initialized` thành `true` nhưng vẫn cần gửi hook tư vấn/lookbook cho tin đầu.
- Nếu bài viết không có mã sản phẩm, gọi AI bằng nguyên text comment của khách.
- Chỉ làm giàu payload gửi `FB_AI_CHAT_URL`; user message lưu trong lịch sử vẫn giữ nguyên comment gốc.
- Chưa gửi reply nếu phần gửi API chưa được bật hoặc thiếu dữ liệu bắt buộc.

Trong phần 1, mục tiêu không phải gửi reply ngay, mà là đảm bảo backend nhận đúng, phân loại đúng, lưu đúng và có đủ dữ liệu để phần 2 gửi API.

### Metadata lưu message

User message comment nên lưu các meta chính:

- `source = pancake_webhook_comment`
- `page_id`
- `sender_id`
- `platform_sender_id`
- `page_customer_id`
- `pancake_conversation_id`
- `message_type = COMMENT`
- `comment_message_id`
- `post_id`
- `post_type`
- `post_message_present`
- `post_message_length`
- `post_product_codes`
- `post_product_code_count`
- `comment_ai_message_augmented`
- `comment_ai_initial_product_prompt`
- `comment_ai_follow_up`
- `conversation_was_ai_initialized`

Không lưu token. Không bắt buộc lưu full raw `data.post.message`; nếu cần audit, ưu tiên lưu preview đã truncate.

### Lỗi cần xử lý an toàn ở phần 1

- Thiếu `page_id`: ignore, không gọi AI.
- Thiếu `pancake_conversation_id`: ignore, không gọi AI.
- Thiếu `comment_message_id`: ignore, không gọi AI.
- Thiếu `sender_id`: ignore, không tạo conversation.
- Thiếu text comment: lưu nếu cần audit, nhưng không gọi AI.
- Comment từ page/admin/automation: không auto reply.
- Duplicate `message_mid`: không xử lý lần hai.
- Dangerous keyword blocked: không gọi AI.
- Conversation đang pause: không gọi AI.

## Phần 2. Gửi reply comment qua Pancake API

Mục tiêu của phần 2 là dùng dữ liệu đã normalize và xác thực ở phần 1 để gửi phản hồi công khai vào đúng comment. Phần này chỉ chạy khi phần 1 đã xác định đủ `page_id`, `pancake_conversation_id`, `comment_message_id` và reply text.

### Điều kiện trước khi gửi

Trước khi gọi Pancake API, backend phải kiểm tra:

- Feature flag comment auto reply đang bật.
- `page_id` có giá trị.
- `pancake_conversation_id` có giá trị.
- `comment_message_id` có giá trị.
- Reply text không rỗng.
- Conversation chưa bị admin pause tại thời điểm chuẩn bị gửi.
- Message không phải duplicate.
- Comment không thuộc page/admin/automation echo.

Nếu thiếu một trong các điều kiện trên, không gọi Pancake API.

### API Pancake cần bổ sung

Endpoint gửi vẫn là endpoint message hiện có của Pancake:

- Path dùng `page_id`.
- Path dùng `pancake_conversation_id`.
- Query dùng `page_access_token` lấy từ mapping token theo `page_id`.

Body gửi comment reply cần có:

- `action = reply_comment`
- `message_id = comment_message_id`
- `message = reply_text`

Nếu phản hồi AI có ảnh Drive, ảnh được gửi bằng request riêng:

- `action = reply_comment`
- `message_id = comment_message_id`
- `content_ids = [content_id]`

`content_id` phải được lấy từ API upload content của Pancake. Mỗi request media gửi một `content_id` và không gửi kèm `message`.

Không nên overload helper `send_pancake_reply` hiện có bằng cách chỉ đổi `action`, vì `reply_comment` cần thêm `message_id`. Nên có wrapper riêng để contract rõ và dễ test.

Đề xuất bổ sung trong [app/services/pancake_message_service.py](../app/services/pancake_message_service.py):

- Constant `PANCAKE_REPLY_COMMENT_ACTION`.
- Helper build payload reply comment.
- Helper build payload media reply comment.
- Hàm `send_pancake_comment_reply`.
- Hàm `send_pancake_comment_content_ids`.
- Validation riêng cho `comment_message_id`.
- Reuse token mapping, timeout, retry và classify lỗi hiện có.

Validation tối thiểu:

- Thiếu `page_id`: return `missing_page_id`.
- Thiếu `conversation_id`: return `missing_pancake_conversation_id`.
- Thiếu `comment_message_id`: return `missing_pancake_comment_message_id`.
- Thiếu `message`: return `missing_reply_message`.
- Thiếu token page: reuse reason `missing_pancake_page_access_token_for_page`.

### Tích hợp gửi trong webhook

Sau khi AI trả text thành công, backend tiếp tục:

- Reload conversation để kiểm tra pause lần cuối.
- Nếu pause mới xuất hiện, không gửi reply.
- Gọi `send_pancake_comment_reply`.
- Nếu AI trả link Drive, reuse pipeline hiện có để tách link, lookup folder, chọn ảnh và bắt buộc có file local.
- Sau khi text reply thành công, upload từng file lên Pancake để lấy `content_id`, rồi gọi `send_pancake_comment_content_ids` vào cùng comment gốc.
- Lưu bot message với `reply_action = reply_comment`.
- Lưu `comment_message_id` trong bot meta.
- Lưu `pancake_send_result`.
- Update `conversation.updated_at`.

Return nên cùng style với flow Pancake hiện có, có thêm:

- `message_kind = customer_comment`
- `reply_action = reply_comment`
- `comment_message_id`
- `reply_result`

### Gửi media trong comment reply

Luồng comment reuse logic ảnh Pancake hiện có:

- Tách Drive folder/file link khỏi nội dung AI và làm sạch text trước khi gửi.
- Lookup ảnh trong folder, chọn ảnh theo màu và giới hạn ảnh hiện có.
- Cache/download ảnh để có file local hợp lệ.
- Gửi text trước bằng `send_pancake_comment_reply`.
- Chỉ khi text thành công mới upload từng file local qua Pancake `upload_contents`.
- Lấy `content_id` Pancake trả về và gửi bằng `send_pancake_comment_content_ids`.
- Payload ảnh luôn có `message_id = comment_message_id`, một `content_id` trong `content_ids` và không có `message`.
- Không gửi URL Google Drive trực tiếp tới Facebook hoặc nền tảng nguồn.
- Không ghi `content_id` đã dùng cho comment vào cache reuse dùng chung, tránh tái sử dụng media ID đã được gửi.
- Nếu lookup/gửi ảnh lỗi, giữ kết quả text thành công và lưu `pancake_drive_image_send_result` để debug.
- Không dùng payload `content_ids` kiểu inbox vì payload đó thiếu `message_id`.

Contract media đã được xác nhận thật ngày 11/06/2026: upload file qua Pancake trả `type = PHOTO` và `content_id`; payload `reply_comment` gồm `message_id + content_ids` trả `success = true` và webhook echo có `attachment_count = 1`. Luồng `content_url` bị loại bỏ vì Facebook có thể nhận ảnh nhưng giao diện Pancake chỉ hiện media lỗi.

### Lỗi cần xử lý an toàn ở phần 2

- Thiếu token theo page: không gửi, log reason.
- Pancake auth/permission error: không retry vô hạn.
- Pancake payload error: không retry vô hạn.
- Pancake 404 conversation: không retry vô hạn.
- Pancake request timeout/lỗi tạm thời: retry theo config hiện có.
- AI response rỗng: không gửi.
- Conversation bị pause trước khi gửi: không gửi.
- Send failed: lưu reason/send result để debug.

## Logging

Nên bổ sung log theo các bước:

- `PANCAKE_COMMENT_WEBHOOK_DETECTED`
- `PANCAKE_COMMENT_NORMALIZED`
- `PANCAKE_COMMENT_DUPLICATE_SKIPPED`
- `PANCAKE_COMMENT_AI_START`
- `PANCAKE_COMMENT_AI_OK`
- `PANCAKE_COMMENT_AI_FAILED`
- `PANCAKE_COMMENT_REPLY_SEND_START`
- `PANCAKE_COMMENT_REPLY_SEND_OK`
- `PANCAKE_COMMENT_REPLY_SEND_FAILED`
- `PANCAKE_COMMENT_REPLY_SUPPRESSED_BY_ADMIN_PAUSE`

Field nên log:

- `page_id`
- `pancake_conversation_id`
- `conversation_id` nội bộ nếu đã có
- `customer_id`
- `message_mid`
- `comment_message_id`
- `post_id`
- `message_type`
- `text_present`
- `text_length`
- `send_status_code`
- `reason`

Không log:

- `page_access_token`
- URL đầy đủ có query token
- Raw full post/comment quá dài
- Dữ liệu khách nhạy cảm không cần thiết

## Cấu hình backend

Nên thêm feature flag để rollout an toàn:

- `PANCAKE_COMMENT_AUTO_REPLY_ENABLED`: bật/tắt flow comment auto reply, mặc định `false`.

Cấu hình hiện có dùng lại:

- `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID`: mapping `page_id -> page_access_token`.
- `PANCAKE_API_TIMEOUT_SECONDS`: timeout Pancake API.
- `PANCAKE_API_RETRY_ATTEMPTS`: số lần retry.
- `PANCAKE_API_RETRY_BACKOFF_SECONDS`: backoff retry.
- `PANCAKE_ADMIN_TAKEOVER_PAUSE_MINUTES`: pause bot khi admin tham gia.
- `PANCAKE_INBOX_IMAGE_MAX_COUNT`: số ảnh tối đa chọn cho mỗi Drive folder link khi reply inbox.
- `PANCAKE_COMMENT_IMAGE_MAX_COUNT`: số ảnh tối đa chọn cho mỗi Drive folder link khi reply comment.
- `FB_AI_CHAT_URL`: endpoint AI Agent.
- `FB_AI_BEARER_TOKEN`: bearer token gọi AI Agent.
- `FB_AI_RETRY_ATTEMPTS`: retry AI.
- `FB_AI_RETRY_BACKOFF_SECONDS`: backoff retry AI.

Optional cho phase sau:

- `PANCAKE_COMMENT_REPLY_SENDER_ID`: sender user id nếu business muốn chỉ định nhân viên/user gửi comment.
- `PANCAKE_COMMENT_REPLY_WITH_MENTION_ENABLED`: bật mention khách khi đã test offset/length thực tế.

## Danh sách file dự kiến thay đổi khi implement

- [app/core/config.py](../app/core/config.py)
- [app/api/v1/pancake_webhook.py](../app/api/v1/pancake_webhook.py)
- [app/services/pancake_webhook_normalize_service.py](../app/services/pancake_webhook_normalize_service.py)
- [app/services/pancake_message_service.py](../app/services/pancake_message_service.py)
- [tests/test_pancake_webhook.py](../tests/test_pancake_webhook.py)
- [tests/test_pancake_message_service.py](../tests/test_pancake_message_service.py)

Nếu muốn tách helper cho dễ test:

- `app/services/pancake_comment_reply_service.py`
- `tests/test_pancake_comment_reply_service.py`

## Checklist implementation tổng hợp

Trạng thái hiện tại: Phase 1-4 đã hoàn thành ở mức code và automated test. Backend nhận diện `COMMENT`, tách `comment_message_id` khỏi `post_id`, làm giàu nội dung AI bằng mã sản phẩm khi có, gửi text reply công khai bằng `reply_comment`, sau đó gửi ảnh lookbook từ Google Drive vào cùng comment khi AI trả link Drive. Với comment follow-up trong conversation đã `fb_ai_initialized = true`, backend không gửi lại hook `{comment}, tư vấn mã sản phẩm {codes}, và gửi ảnh lookbook`; thay vào đó chỉ gửi nguyên text comment của khách như tin nhắn bình thường. Feature flag `PANCAKE_COMMENT_AUTO_REPLY_ENABLED` mặc định `false`; phần còn lại là deploy page test, bật flag có kiểm soát và xác nhận text/ảnh thật trên Pancake.

### Phase 1. Nhận webhook comment/post

- [x] Log webhook comment thật từ Pancake trên page test.
- [x] Xác nhận webhook comment dùng `event_type = messaging`, `event_type = post`, hay cả hai.
- [x] Xác nhận field chính xác của `pancake_conversation_id`.
- [x] Xác nhận field chính xác của `comment_message_id`.
- [x] Xác nhận `data.post.id` là post ID, không phải comment ID.
- [x] Chốt webhook nào đủ dữ liệu để xử lý tiếp.
- [x] Chốt webhook nào chỉ log/ignore vì chỉ có post info.

### Phase 2. Normalize và xử lý webhook comment/post

- [x] Mở rộng normalize để nhận `message_type = COMMENT`.
- [x] Bổ sung `comment_message_id`.
- [x] Bổ sung post metadata an toàn.
- [x] Return reason rõ khi thiếu `conversation_id` hoặc `comment_message_id`.
- [x] Thêm message kind `customer_comment`.
- [x] Không làm đổi behavior của `INBOX`.
- [x] Không làm đổi behavior auto consult ad/comment notice.
- [x] Check dangerous keyword cho text comment.
- [x] Duplicate guard theo `message_mid`.
- [x] Lưu user message comment.
- [x] Tôn trọng admin pause trước khi gọi AI.
- [x] Bóc mã sản phẩm từ full `data.post.message` bằng regex dùng chung với auto consult.
- [x] Nếu có mã và conversation chưa init AI trước webhook hiện tại, gửi AI theo format `{comment}, tư vấn mã sản phẩm {codes}, và gửi ảnh lookbook`.
- [x] Nếu có mã nhưng conversation đã init AI trước webhook hiện tại, gửi nguyên text comment sang AI và không lặp lại hook tư vấn/lookbook.
- [x] Nếu không có mã, gửi nguyên text comment sang AI.
- [x] Giữ nguyên comment gốc khi lưu user message.
- [x] Log `product_code_count` và trạng thái payload có được làm giàu hay không.

### Phase 3. Bổ sung API gửi reply comment

- [x] Thêm constant `PANCAKE_REPLY_COMMENT_ACTION = "reply_comment"`.
- [x] Thêm helper build payload reply comment.
- [x] Thêm `send_pancake_comment_reply`.
- [x] Thêm helper build payload media reply comment với `message_id` và `content_ids`.
- [x] Thêm `send_pancake_comment_content_ids`.
- [x] Validate đủ `page_id`, `conversation_id`, `comment_message_id`, `message`.
- [x] Validate media đủ `page_id`, `conversation_id`, `comment_message_id`, `content_ids`.
- [x] Dùng token mapping theo `page_id`.
- [x] Reuse timeout/retry/error classify hiện có.
- [x] Không log token hoặc URL có token.
- [x] Test validation thiếu dữ liệu bắt buộc.

### Phase 4. Tích hợp gửi comment reply và test rollout

- [x] Sau AI success, kiểm tra admin pause lần cuối trước khi gửi.
- [x] Gửi `send_pancake_comment_reply`.
- [x] Không gửi `reply_inbox` cho comment.
- [x] Lưu bot message với `reply_action = reply_comment`.
- [x] Lưu `comment_message_id` trong bot meta.
- [x] Lưu Pancake send result.
- [x] Reuse logic tách link Drive, lookup folder, chọn ảnh và cache/download hiện có.
- [x] Gửi text trước, ảnh sau.
- [x] Upload ảnh vào Pancake để lấy `content_id` trước khi reply comment.
- [x] Gửi ảnh bằng `reply_comment` có đúng `comment_message_id`.
- [x] Không gửi ảnh comment bằng `reply_inbox`.
- [x] Không gửi URL Drive trực tiếp tới nền tảng nguồn.
- [x] Lưu `pancake_drive_image_send_result` trong bot meta.
- [x] Test normalize comment happy path.
- [x] Test post event thuần bị ignore vì thiếu comment ID/conversation ID.
- [x] Test không dùng `data.post.id` làm `message_id`.
- [x] Test service gửi đúng body reply comment.
- [x] Test webhook comment gọi AI và gửi `reply_comment`.
- [x] Test webhook comment có ảnh gọi pipeline Drive với `reply_comment`.
- [x] Test payload ảnh comment có `message_id` và `content_ids`.
- [x] Test mỗi ảnh được upload Pancake trước khi gửi media reply.
- [x] Test duplicate comment không gọi AI/gửi lần hai.
- [x] Test paused conversation không gọi AI/gửi.
- [x] Test missing `comment_message_id` không gọi Pancake.
- [x] Test page/admin/automation comment không auto reply.
- [x] Chạy `pytest -q`.

Task list chi tiết từng phase:

- [Phase 1. Nhận webhook comment/post](pancake-webhook-reply-comment/phase-1.md)
- [Phase 2. Normalize và xử lý webhook comment/post](pancake-webhook-reply-comment/phase-2.md)
- [Phase 3. Bổ sung API gửi reply comment](pancake-webhook-reply-comment/phase-3.md)
- [Phase 4. Tích hợp gửi comment reply và test rollout](pancake-webhook-reply-comment/phase-4.md)

## Test cần có khi implement

- `normalize_pancake_payload` trả `ok = True` với customer comment đủ field.
- `normalize_pancake_payload` set `message_type = COMMENT`.
- `normalize_pancake_payload` set `comment_message_id` từ comment payload.
- `normalize_pancake_payload` map `post_id` từ `data.post.id`.
- `normalize_pancake_payload` không nhầm `post_id` với `comment_message_id`.
- `normalize_pancake_payload` trả reason thiếu `pancake_conversation_id`.
- `normalize_pancake_payload` trả reason thiếu `comment_message_id`.
- `_classify_pancake_message` trả `customer_comment` cho comment khách.
- `_classify_pancake_message` không trả `customer_comment` cho page sender.
- Helper resolve reply action trả `reply_comment` cho `COMMENT`.
- Helper build payload reply comment tạo body đúng contract.
- Helper build payload ảnh reply comment tạo đúng `action`, `message_id`, `content_ids`.
- `send_pancake_comment_reply` gọi đúng URL và query token theo `page_id`.
- `send_pancake_comment_content_ids` gọi đúng URL và query token theo `page_id`.
- `send_pancake_comment_reply` không gửi khi thiếu `comment_message_id`.
- `_process_normalized_message` comment happy path lưu user message, gọi AI, gửi comment reply và lưu bot message.
- `_process_normalized_message` không gọi AI nếu dangerous keyword blocked.
- `_process_normalized_message` không gọi AI nếu duplicate.
- `_process_normalized_message` không gửi nếu conversation paused.
- `_process_normalized_message` không gửi `reply_inbox` cho comment.
- `_generate_pancake_reply` gửi hook tư vấn/lookbook khi conversation chưa init AI trước webhook hiện tại.
- `_generate_pancake_reply` gửi nguyên text comment và không lặp hook tư vấn/lookbook khi conversation đã init AI trước webhook hiện tại.
- `_process_normalized_message` gửi ảnh Drive sau khi text comment thành công.
- Pipeline ảnh comment upload file vào Pancake và không gọi helper `content_ids` của inbox.
- Bot message meta có `reply_action = reply_comment`.
- Không lưu token trong `Message.meta`.

## Ghi chú production

- Bật feature flag trên page test trước khi bật rộng.
- Quan sát log thực tế để xác nhận schema webhook comment trước khi code assume field cố định.
- Không reply nếu thiếu một trong ba ID bắt buộc: `page_id`, `pancake_conversation_id`, `comment_message_id`.
- Không retry vô hạn với lỗi auth/permission/payload.
- Theo dõi tỉ lệ `missing_pancake_comment_message_id` và `missing_pancake_conversation_id`; nếu cao, cần bổ sung bước resolve conversation từ Pancake API sau.
- Test thật một comment có Drive folder để xác nhận Pancake hiển thị text trước và ảnh sau trong đúng thread comment.
- Nếu dùng mentions, phải test offset/length với Unicode tiếng Việt vì sai offset có thể làm API reject hoặc mention nhầm.
