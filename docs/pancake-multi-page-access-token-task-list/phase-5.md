# Task List Phase 5: Test và rollout multi-page Pancake token

## Mục tiêu

Phase 5 hoàn thiện test coverage và rollout cho multi-page Pancake token. Toàn bộ test phải dùng mock, không gọi Pancake thật, và phải chứng minh không có fallback sang token mặc định khi thiếu token theo page.

Kết quả mong muốn:

- Unit test cover config parse/token lookup.
- Service test cover text reply/upload/content_ids đúng token theo page.
- Webhook test cover nhiều page dùng nhiều token.
- Error path thiếu token không gọi HTTP.
- `pytest -q` pass.
- Rollout production có checklist theo page.

## Đầu vào đã chốt

- Tests không cần external service.
- Pancake HTTP client được mock.
- Env/settings được monkeypatch trong test.
- Missing token là non-retryable.
- Không fallback sang `PANCAKE_PAGE_ACCESS_TOKEN`.

## Ngoài phạm vi Phase 5

- Không gọi Pancake thật.
- Không test token thật.
- Không benchmark performance parse env.
- Không test UI/secret manager.

## File chính dự kiến sửa

- [tests/test_pancake_message_service.py](../../tests/test_pancake_message_service.py)
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)
- Test helper/fixture nếu cần.

## Checklist

### 1. Test config parser

- [x] Parse mapping JSON hợp lệ.
- [x] Parse mapping nhiều page.
- [x] Strip whitespace ở key/value.
- [x] Bỏ entry key rỗng.
- [x] Bỏ entry value rỗng.
- [x] Env missing trả `missing_pancake_page_access_tokens_by_page_id`.
- [x] Env invalid JSON trả `invalid_pancake_page_access_tokens_by_page_id`.
- [x] Env JSON array trả invalid.
- [x] Env JSON string trả invalid.

Kết quả mong muốn:
  Parser hoạt động ổn định với env production thường gặp.

### 2. Test token lookup

- [x] Lookup page A trả token A.
- [x] Lookup page B trả token B.
- [x] Lookup page id có whitespace vẫn đúng.
- [x] Lookup page chưa cấu hình trả `missing_pancake_page_access_token_for_page`.
- [x] Missing `page_id` trả `missing_page_id`.
- [x] Có `PANCAKE_PAGE_ACCESS_TOKEN` cũ nhưng lookup page thiếu token vẫn lỗi.
- [x] Error object không chứa token.

Kết quả mong muốn:
  Helper lookup enforce đúng rule không fallback.

### 3. Test Pancake message service

- [x] `send_pancake_reply` page A gọi HTTP với token A.
- [x] `send_pancake_reply` page B gọi HTTP với token B.
- [x] `send_pancake_reply` page thiếu token không gọi HTTP.
- [x] `upload_pancake_content` page A gọi HTTP với token A.
- [x] `upload_pancake_content` page thiếu token không mở/gửi file nếu có thể kiểm tra.
- [x] `send_pancake_content_ids` page B gọi HTTP với token B.
- [x] `send_pancake_content_ids` page thiếu token không gọi HTTP.
- [x] Retry không chạy khi missing token.

Kết quả mong muốn:
  Mọi API wrapper đều dùng token theo page và fail closed.

### 4. Test webhook flow

- [x] Webhook page A gửi text reply bằng token A.
- [x] Webhook page B gửi text reply bằng token B.
- [x] Webhook page thiếu token không gửi text reply.
- [x] Webhook page thiếu token vẫn lưu user message.
- [x] Webhook page thiếu token trả/lưu reason rõ.
- [x] Drive image upload page A dùng token A.
- [x] Reuse `content_id` page B gửi image message bằng token B.
- [x] Admin takeover/duplicate guard không bị regression.

Kết quả mong muốn:
  Behavior end-to-end đúng với nhiều page và không gửi nhầm token.

### 5. Test logging/security

- [x] Token không xuất hiện trong captured logs.
- [x] Raw env mapping không xuất hiện trong captured logs.
- [x] Error response không chứa token.
- [x] URL đầy đủ có token không bị log.
- [x] Missing token log có `page_id` và reason.

Kết quả mong muốn:
  Test bảo vệ chống lộ token ở các path lỗi chính.

### 6. Rollout

- [x] Chạy `pytest -q`.
- [x] Kiểm tra `.env.example` không có token thật.
- [ ] Validate JSON env production trước deploy.
- [ ] Test từng page ở staging hoặc page test.
- [ ] Theo dõi reason `missing_pancake_page_access_token_for_page`.
- [ ] Theo dõi Pancake auth error theo page.
- [ ] Xác nhận reply đúng page/conversation.

Kết quả mong muốn:
  Có thể rollout multi-page token có kiểm soát.

## Acceptance criteria

- [x] Config parser tests pass.
- [x] Token lookup tests pass.
- [x] Pancake service tests pass.
- [x] Webhook multi-page mock tests pass.
- [x] Security/logging tests pass.
- [x] `pytest -q` pass.
- [x] Rollout checklist được review.

## Ghi chú mở

- Nếu platform production có syntax env khác local `.env`, cần ghi chú riêng trong runbook deploy.
- Nếu token được rotate, test staging lại đúng page vừa rotate trước khi deploy production.
