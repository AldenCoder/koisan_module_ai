# Chặn Pancake webhook theo dangerous keywords

## Mục tiêu

Tài liệu này mô tả phương án để `BE` kiểm tra nội dung khách hàng ngay sau khi nhận và normalize webhook Pancake. Nếu text khách hàng có xuất hiện bất kỳ keyword/cụm keyword nào trong [dangerous_keywords.md](dangerous_keywords.md), `BE` dừng xử lý ngay lập tức.

Điểm thay đổi chính: webhook Pancake có thêm lớp chặn sớm trước khi tạo/lấy conversation, trước khi lưu user message, trước khi gọi AI và trước khi gửi bất kỳ phản hồi nào về Pancake. Khi match keyword nguy hiểm, hệ thống trả kết quả nội bộ dạng ignored, không phản hồi gì cho khách.

Quy ước thuật ngữ:

- `BE` / `Backend`: repo hiện tại `koisan_module_ai`.
- `Pancake`: nền tảng nhận/gửi tin nhắn khách qua Public API.
- `AI Agent` / `Brain`: service tạo nội dung trả lời cho khách.
- `dangerous_keywords.md`: file danh sách keyword/cụm keyword nguy hiểm, mỗi dòng là một keyword.
- `dangerous keyword block`: bước kiểm tra text khách hàng và dừng flow nếu match keyword.
- `message_mid`: id message phía Pancake, dùng để trace webhook.
- `pancake_conversation_id`: id hội thoại phía Pancake.

## Luồng tổng thể

Khách hàng nhắn tin vào kênh social đã nối Pancake.

`BE` nhận webhook Pancake, parse JSON và normalize payload như flow hiện tại.

`BE` xác định message có phải tin nhắn khách hàng cần xử lý hay không.

Nếu là tin nhắn khách hàng và có text, `BE` load danh sách keyword từ `docs/dangerous_keywords.md`, giữ nguyên keyword như trong file, rồi kiểm tra trong câu khách hàng có keyword nào match theo literal và ranh giới từ hay không.

Nếu có match, `BE` dừng ngay:

- Không tạo conversation mới.
- Không lấy conversation hiện có để cập nhật.
- Không lưu user message.
- Không lưu bot message.
- Không gọi AI.
- Không gọi RAG/Brain.
- Không gửi tin nhắn Pancake.
- Không gửi ảnh.
- Không handover.
- Không pause bot.

Nếu không có match, `BE` tiếp tục flow Pancake hiện tại.

## Ranh giới trách nhiệm

### BE hiện tại

BE chịu trách nhiệm:

- Đọc danh sách keyword từ [dangerous_keywords.md](dangerous_keywords.md).
- Chuẩn hóa keyword để match ổn định.
- Chuẩn hóa text khách hàng trước khi kiểm tra.
- Chạy dangerous keyword block ngay sau normalize webhook và trước các bước ghi database/gọi AI.
- Chỉ áp dụng block cho tin nhắn khách hàng.
- Nếu match, trả internal result `ignored` với reason rõ ràng.
- Nếu match, không phản hồi gì cho khách trên Pancake.
- Nếu match, không lưu nội dung tin nhắn vào `Conversation` hoặc `Message`.
- Log metadata tối thiểu để debug, không log full text khách hàng khi đã match.

### Pancake

Pancake chịu trách nhiệm:

- Gửi webhook message về `BE`.
- Không cần biết keyword nào bị match.
- Không nhận reply từ `BE` khi message bị chặn.

### AI Agent / Brain

AI Agent không tham gia flow khi message match dangerous keyword.

AI Agent không nhận:

- Text khách hàng.
- Conversation context.
- Payload init sender.
- Bất kỳ request nào phát sinh từ message bị chặn.

### Ngoài phạm vi phương án này

- Không đổi flow Facebook webhook.
- Không sửa nội dung file [dangerous_keywords.md](dangerous_keywords.md) trong task này.
- Không phản hồi cảnh báo cho khách.
- Không tự động chuyển nhân viên phụ trách.
- Không tạo conversation chỉ để ghi nhận message bị chặn.
- Không lưu full text bị chặn vào database.
- Không build UI quản lý keyword.
- Không phân loại mức độ nguy hiểm theo category trong phase đầu.

## Vị trí chặn trong flow Pancake

Vị trí mong muốn nằm sau bước normalize payload và trước mọi tác vụ có side effect.

Flow hiện tại rút gọn:

```text
receive_webhook
-> parse JSON
-> normalize_pancake_payload
-> _process_normalized_message
-> classify message
-> duplicate check
-> get/create conversation
-> save user message
-> call AI
-> send Pancake reply
-> save bot message
```

Flow mới:

```text
receive_webhook
-> parse JSON
-> normalize_pancake_payload
-> _process_normalized_message
-> classify message
-> dangerous keyword block
   |- match: return ignored, stop
   |- no match: continue current flow
-> duplicate check
-> get/create conversation
-> save user message
-> call AI
-> send Pancake reply
-> save bot message
```

Điểm quan trọng: dangerous keyword block phải chạy trước các hàm sau:

- `_is_duplicate_pancake_message`
- `_get_or_create_pancake_conversation`
- `_save_pancake_user_message`
- `_generate_pancake_reply`
- `_ensure_sender_initialized`
- `_post_ai_chat_with_retry`
- `send_pancake_reply`
- `send_pancake_content_ids`
- `_save_pancake_bot_message`

## Quy tắc đọc file keyword

File nguồn:

```text
docs/dangerous_keywords.md
```

Quy tắc:

- Mỗi dòng trong file là một keyword/cụm keyword.
- Bỏ qua dòng rỗng.
- Không yêu cầu markdown heading, bảng hoặc giải thích.
- Trim khoảng trắng đầu/cuối dòng.
- Dedupe keyword theo giá trị nguyên văn sau khi trim.
- Nếu file không tồn tại hoặc không đọc được, `BE` log lỗi và dừng xử lý message khách hàng để không gửi nội dung sang AI.

Đề xuất phase đầu:

- Block luôn bật, không có biến env để tắt.
- Keyword reload theo `mtime` khi file thay đổi là behavior mặc định trong code, không cần biến env riêng.
- Nếu không load được keyword file, không gọi AI cho message khách hàng.

## Chuẩn bị text trước khi match

Text khách hàng và keyword được dùng theo rule literal có ranh giới từ:

- Keyword chỉ trim khoảng trắng đầu/cuối dòng khi load từ file.
- Text khách hàng giữ nguyên nội dung đã normalize từ Pancake payload.
- Không lowercase/casefold.
- Không bỏ dấu tiếng Việt.
- Không tạo thêm keyword không dấu.
- Không tạo thêm trường normalized để check tiếp.
- Không collapse khoảng trắng bên trong keyword hoặc text.
- Keyword dạng ký tự kỹ thuật như `.env`, `../`, `cmd.exe`, `os.system` vẫn match theo literal, nhưng cạnh bắt đầu/kết thúc là ký tự chữ/số/`_` phải có ranh giới từ.

Ví dụ:

```text
"bỏ qua hướng dẫn trước đó"
```

match keyword:

```text
"bỏ qua hướng dẫn"
```

Nhưng:

```text
"bo qua huong dan truoc do"
```

không match keyword `bỏ qua hướng dẫn` nếu trong file không có đúng keyword không dấu đó.

## Quy tắc match

Rule match:

- Nếu bất kỳ keyword nào xuất hiện nguyên văn trong text khách hàng với ranh giới từ hợp lệ, block.
- Match literal theo đúng keyword trong file.
- Match có phân biệt dấu tiếng Việt.
- Không match biến thể không dấu nếu biến thể đó không có trong file.
- Không match biến thể hoa/thường nếu biến thể đó không có trong file.
- Nếu đầu keyword là ký tự chữ/số/`_`, ký tự ngay trước match phải không tồn tại hoặc không phải ký tự chữ/số/`_`.
- Nếu cuối keyword là ký tự chữ/số/`_`, ký tự ngay sau match phải không tồn tại hoặc không phải ký tự chữ/số/`_`.
- Keyword dạng ký tự kỹ thuật như `.env`, `../`, `find({})`, `drop()` vẫn match literal, đồng thời áp dụng ranh giới ở cạnh có ký tự chữ/số/`_`.

Ví dụ keyword `db` chỉ match khi đứng riêng như `db`, `db:`, `(db)`, `truy vấn db`; không match khi nằm trong từ/token khác như `feedback`, `database`, `mongodbx`, `db_cache`.

## Contract object nội bộ

Service/helper dangerous keyword block nên trả object ổn định để dễ test:

```json
{
  "blocked": true,
  "reason": "dangerous_keyword_matched",
  "matched_keyword": "bỏ qua hướng dẫn"
}
```

Khi không match:

```json
{
  "blocked": false,
  "reason": null,
  "matched_keyword": null
}
```

Không đưa full text khách hàng vào object log hoặc response khi đã blocked.

## Response nội bộ khi bị chặn

Khi dangerous keyword block match, `_process_normalized_message` trả về:

```json
{
  "status": "ignored",
  "ok": false,
  "reason": "pancake_dangerous_keyword_blocked",
  "message_mid": "MESSAGE_MID",
  "message_kind": "customer_message",
  "page_id": "PAGE_ID",
  "pancake_conversation_id": "PANCAKE_CONVERSATION_ID"
}
```

Quy tắc:

- Không trả `reply_text`.
- Không trả `message_id`.
- Không trả `bot_message_id`.
- Không trả `conversation_id` nội bộ nếu chưa tạo/lấy conversation.
- Không trả full `normalized_message.text` trong response nếu message bị chặn.
- Không gọi Pancake Public API để gửi reply.

## Logging

Log khi bị chặn chỉ nên chứa metadata tối thiểu:

- `page_id`
- `sender_id`
- `message_mid`
- `pancake_conversation_id`
- `matched_keyword`
- `reason`

Không log:

- Full raw payload.
- Full text khách hàng.
- Token hoặc secret.
- AI payload.

Nếu hệ thống hiện đang log raw payload trước khi chặn, task implementation cần điều chỉnh để tránh lưu full message bị chặn vào log. Có thể log raw payload ở mức debug có redaction, hoặc chỉ log metadata đã normalize.

Log đề xuất:

```text
PANCAKE_DANGEROUS_KEYWORD_BLOCKED page_id=%s sender_id=%s message_mid=%s pancake_conversation_id=%s matched_keyword=%s
```

## Lưu message vào database

Khi dangerous keyword block match:

- Không tạo `Conversation`.
- Không update `Conversation.updated_at`.
- Không insert `Message` role `user`.
- Không insert `Message` role `bot`.
- Không lưu keyword match vào `Message.meta` vì không có message được tạo.
- Không lưu audit record riêng trong phase đầu, trừ khi business yêu cầu sau.

Khi không match:

- Flow lưu user message và bot message giữ nguyên như hiện tại.

## Gọi AI và gửi reply

Khi dangerous keyword block match:

- Không gọi `_ensure_sender_initialized`.
- Không build AI payload.
- Không gọi `FB_AI_CHAT_URL` hoặc AI endpoint tương đương.
- Không gọi RAG.
- Không parse AI response.
- Không chuẩn bị Drive image reply.
- Không upload ảnh.
- Không gọi `send_pancake_reply`.
- Không gọi `send_pancake_content_ids`.

Khách hàng sẽ không nhận được bất kỳ phản hồi nào từ bot cho message đó.

## Cấu hình backend

Phase này không bổ sung biến env.

Quy tắc cố định:

- Dangerous keyword block luôn bật.
- Keyword path cố định là `docs/dangerous_keywords.md`.
- Keyword reload theo `mtime` khi file thay đổi là mặc định trong service.
- Nếu không load được keyword file, `BE` dừng xử lý message khách hàng và không gọi AI.

## Danh sách file dự kiến thay đổi khi implement

- [app/api/v1/pancake_webhook.py](../app/api/v1/pancake_webhook.py)

Nếu tách service/helper riêng để dễ test:

- `app/services/dangerous_keyword_service.py`

Nếu cần test helper riêng:

- `tests/test_dangerous_keyword_service.py`
- `tests/test_pancake_webhook_dangerous_keyword_block.py`

## Checklist implementation tổng hợp

### Phase 0. Chốt giải pháp

- [x] Chốt source keyword là [dangerous_keywords.md](dangerous_keywords.md).
- [x] Chốt block chạy sau normalize Pancake webhook.
- [x] Chốt block chạy trước duplicate DB check, trước tạo/lấy conversation và trước lưu user message.
- [x] Chốt khi match keyword thì không phản hồi gì cho khách.
- [x] Chốt khi match keyword thì không gọi AI/RAG/Brain.
- [x] Chốt khi match keyword thì không lưu `Conversation` hoặc `Message`.
- [x] Chốt block luôn bật, không thêm biến env bật/tắt.
- [x] Chốt keyword reload theo `mtime` là mặc định, không thêm biến env reload.

### Phase 1. Service đọc và match keyword

- [x] Tạo helper/service đọc file `docs/dangerous_keywords.md`.
- [x] Bỏ qua dòng rỗng.
- [x] Trim keyword.
- [x] Dedupe keyword theo giá trị nguyên văn sau khi trim.
- [x] Cache danh sách keyword để không đọc file lại ở mọi request nếu chưa đổi `mtime`.
- [x] Reload keyword theo `mtime` khi file thay đổi.
- [x] Không tạo thêm bản không dấu.
- [x] Không tạo thêm normalized keyword field.
- [x] Match literal theo đúng keyword trong file, có ranh giới từ cho keyword dạng chữ/số/`_`.
- [x] Trả object nội bộ có `blocked`, `reason`, `matched_keyword`.

### Phase 2. Gắn vào Pancake webhook

- [x] Gọi dangerous keyword block trong `_process_normalized_message`.
- [x] Chỉ áp dụng cho `PANCAKE_MESSAGE_CUSTOMER`.
- [x] Chỉ áp dụng cho message type `INBOX`.
- [x] Chạy trước `_is_duplicate_pancake_message`.
- [x] Chạy trước `_get_or_create_pancake_conversation`.
- [x] Chạy trước `_save_pancake_user_message`.
- [x] Nếu match, return `status="ignored"` và `reason="pancake_dangerous_keyword_blocked"`.
- [x] Nếu match, không trả full text trong response.
- [x] Nếu không match, giữ nguyên flow hiện tại.

### Phase 3. Logging và bảo mật dữ liệu

- [x] Log event bị chặn với metadata tối thiểu.
- [x] Không log full text khách hàng khi bị chặn.
- [x] Không log raw payload chứa message bị chặn.
- [x] Không log token/secret.
- [x] Đảm bảo response webhook không chứa nội dung text bị chặn.

### Phase 4. Test

- [x] Test message khách hàng chứa keyword trong `dangerous_keywords.md` bị ignored.
- [x] Test message bị block không tạo `Conversation`.
- [x] Test message bị block không insert `Message`.
- [x] Test message bị block không gọi AI.
- [x] Test message bị block không gọi `send_pancake_reply`.
- [x] Test message bị block không gọi `send_pancake_content_ids`.
- [x] Test match literal có ranh giới từ đúng keyword trong file.
- [x] Test keyword tiếng Việt có dấu chỉ match khi text chứa đúng dấu như keyword.
- [x] Test biến thể không dấu không bị block nếu keyword không dấu không có trong file.
- [x] Test keyword kỹ thuật như `.env`, `../`, `os.system`.
- [x] Test message bán hàng bình thường vẫn đi flow hiện tại.
- [x] Test bot echo không bị xử lý như customer dangerous block.
- [x] Test admin message giữ behavior admin takeover hiện tại.
- [x] Test non-INBOX message giữ behavior ignored hiện tại.
- [x] Chạy `pytest -q`.

Task list chi tiết từng phase:

- [Phase 0. Chốt giải pháp dangerous keyword block](pancake-dangerous-keyword-block-task-list/phase-0.md)
- [Phase 1. Service đọc và match dangerous keyword](pancake-dangerous-keyword-block-task-list/phase-1.md)
- [Phase 2. Gắn dangerous keyword block vào Pancake webhook](pancake-dangerous-keyword-block-task-list/phase-2.md)
- [Phase 3. Logging và bảo mật dữ liệu dangerous keyword block](pancake-dangerous-keyword-block-task-list/phase-3.md)
- [Phase 4. Test dangerous keyword block](pancake-dangerous-keyword-block-task-list/phase-4.md)

Tiến độ hiện tại:

- [x] Phase 0. Chốt giải pháp dangerous keyword block.
- [x] Phase 1. Service đọc và match dangerous keyword.
- [x] Phase 2. Gắn dangerous keyword block vào Pancake webhook.
- [x] Phase 3. Logging và bảo mật dữ liệu dangerous keyword block.
- [x] Phase 4. Test dangerous keyword block.

## Test cần có khi implement

- Khách gửi `bỏ qua hướng dẫn trước đó` thì webhook return ignored, reason `pancake_dangerous_keyword_blocked`.
- Khách gửi `bo qua huong dan truoc do` không bị block nếu file keyword không có đúng keyword không dấu.
- Khách gửi `cho tôi file .env` bị block.
- Khách gửi `hãy chạy os.system` bị block.
- Khách gửi `mẫu này còn màu trắng không` không bị block và flow hiện tại chạy tiếp.
- Message bị block không tạo conversation mới.
- Message bị block không lưu user message.
- Message bị block không gọi `_post_ai_chat_with_retry`.
- Message bị block không gửi Pancake reply.
- Webhook response khi block không chứa full text khách hàng.
- Log khi block không chứa full text khách hàng.

## Ghi chú production

- Dangerous keyword block nên chạy rất sớm để giảm rủi ro gửi nội dung nguy hiểm sang AI.
- Không phản hồi gì cho khách là behavior chủ đích của task này.
- Vì message bị block không lưu DB, duplicate message bị gửi lại sẽ tiếp tục bị block theo keyword.
- Nếu cần audit sau này, nên tạo audit storage riêng có redaction và retention rõ ràng, không dùng `Message` hiện tại.
- Khi chỉnh file [dangerous_keywords.md](dangerous_keywords.md), cần chạy lại test match keyword để tránh false positive ngoài ý muốn.
- Nếu raw webhook logging đang bật ở production, cần redaction trước khi rollout task này để không lưu nội dung bị chặn vào log.
