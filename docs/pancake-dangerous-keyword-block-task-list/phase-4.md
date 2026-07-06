# Task List Phase 4: Test dangerous keyword block

## Mục tiêu

Phase 4 hoàn thiện test coverage cho dangerous keyword block. Tests phải chứng minh rule match literal đúng tài liệu, flow bị block không tạo side effect, flow bình thường không regression, và log/response không lộ full text khách hàng bị chặn.

Kết quả mong muốn:

- Unit test cover service đọc/match keyword.
- Webhook test cover block path.
- Webhook test cover no-match path.
- Test cover bot echo/admin/non-INBOX không bị block sai.
- Test security/logging không lộ full text.
- `pytest -q` pass.

## Đầu vào đã chốt

- Tests không gọi Pancake thật.
- Tests không gọi AI thật.
- Keyword file có thể dùng temp file hoặc monkeypatch service path/cache.
- HTTP/API client được mock.
- DB/service side effects được mock bằng `AsyncMock`.

## Ngoài phạm vi Phase 4

- Không gọi external service.
- Không benchmark performance matcher.
- Không test UI/admin.
- Không test production log collector.
- Không dùng keyword thật để gửi request ra ngoài.

## File chính dự kiến sửa

- `tests/test_dangerous_keyword_service.py`
- `tests/test_pancake_webhook_dangerous_keyword_block.py`
- Hoặc bổ sung vào [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)
- Test helpers/fixtures nếu cần.

## Checklist

### 1. Test service đọc keyword

- [x] Test đọc keyword từ file hợp lệ.
- [x] Test bỏ qua dòng rỗng.
- [x] Test trim khoảng trắng đầu/cuối keyword.
- [x] Test dedupe keyword.
- [x] Test giữ thứ tự keyword sau dedupe.
- [x] Test không lowercase/casefold keyword.
- [x] Test không bỏ dấu keyword.
- [x] Test không collapse khoảng trắng bên trong keyword.
- [x] Test cache không đọc lại file khi `mtime` chưa đổi.
- [x] Test reload khi `mtime` thay đổi.
- [x] Test file không tồn tại trả/raise reason rõ.

Kết quả mong muốn:
  Keyword loader ổn định và đúng rule tài liệu.

### 2. Test match literal có ranh giới từ

- [x] Test `bỏ qua hướng dẫn trước đó` bị block nếu keyword là `bỏ qua hướng dẫn`.
- [x] Test `bo qua huong dan truoc do` không bị block nếu không có keyword không dấu.
- [x] Test keyword hoa/thường phân biệt đúng.
- [x] Test keyword `.env` match trong câu `cho tôi file .env`.
- [x] Test keyword `../` match path traversal.
- [x] Test keyword `os.system` match câu kỹ thuật.
- [x] Test keyword `db` đứng riêng bị block nhưng không match trong `feedback`.
- [x] Test text không chứa keyword trả `blocked=False`.
- [x] Test text rỗng hoặc `None` không match.
- [x] Test result không chứa full text.

Kết quả mong muốn:
  Matcher chứng minh behavior literal có ranh giới từ, không normalize ngầm.

### 3. Test webhook block path

- [x] Test customer message chứa keyword return `status="ignored"`.
- [x] Test reason là `pancake_dangerous_keyword_blocked`.
- [x] Test response có `message_mid`.
- [x] Test response có `page_id`.
- [x] Test response có `pancake_conversation_id`.
- [x] Test response không có full text khách hàng.
- [x] Test không gọi `_is_duplicate_pancake_message`.
- [x] Test không gọi `_get_or_create_pancake_conversation`.
- [x] Test không gọi `_save_pancake_user_message`.
- [x] Test không gọi `_generate_pancake_reply`.
- [x] Test không gọi `_post_ai_chat_with_retry`.
- [x] Test không gọi `send_pancake_reply`.
- [x] Test không gọi `send_pancake_content_ids`.

Kết quả mong muốn:
  Message nguy hiểm bị chặn trước mọi side effect.

### 4. Test no-match và regression guard

- [x] Test message bán hàng bình thường vẫn đi flow hiện tại.
- [x] Test message bình thường vẫn lưu user message.
- [x] Test message bình thường vẫn gọi AI.
- [x] Test message bình thường vẫn gửi Pancake reply.
- [x] Test bot echo không bị xử lý như customer dangerous block.
- [x] Test admin message giữ behavior admin takeover hiện tại.
- [x] Test non-INBOX message giữ behavior ignored hiện tại.
- [x] Test duplicate guard hiện tại không bị regression.

Kết quả mong muốn:
  Lớp block không làm hỏng các flow không nguy hiểm.

### 5. Test logging/security

- [x] Test log block có `page_id`.
- [x] Test log block có `sender_id`.
- [x] Test log block có `message_mid`.
- [x] Test log block có `pancake_conversation_id`.
- [x] Test log block có `matched_keyword`.
- [x] Test log block không chứa full text khách hàng.
- [x] Test response block không chứa full text khách hàng.
- [x] Test raw payload chứa text bị block không xuất hiện trong captured logs.
- [x] Test token/secret không xuất hiện trong captured logs.
- [x] Test lỗi load keyword file không gọi AI và không log full text.

Kết quả mong muốn:
  Test bảo vệ các rủi ro lộ dữ liệu chính của feature.

### 6. Chạy test suite

- [x] Chạy `pytest -q`.
- [x] Kiểm tra không có test gọi external service.
- [x] Kiểm tra không có token/secret thật trong fixtures.
- [x] Kiểm tra warning mới nếu có.

Kết quả mong muốn:
  Feature có thể merge với test suite xanh.

## Acceptance criteria

- [x] Service keyword tests pass.
- [x] Literal boundary tests pass.
- [x] Webhook block path tests pass.
- [x] No-match regression tests pass.
- [x] Logging/security tests pass.
- [x] `pytest -q` pass.

## Ghi chú mở

- Khi chỉnh [docs/dangerous_keywords.md](../dangerous_keywords.md), cần chạy lại nhóm test matcher để bắt false positive/false negative.
- Nếu tách file test mới làm suite quá dài, có thể giữ test service và webhook block ở hai file riêng để dễ bảo trì.
