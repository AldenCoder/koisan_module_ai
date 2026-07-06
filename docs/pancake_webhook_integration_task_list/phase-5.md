# Task List Phase 5: Test và rollout

## Mục tiêu

Phase 5 kiểm tra toàn bộ luồng Pancake từ nhận webhook, normalize payload, lưu conversation/message, gọi AI/rule, đến gửi reply Pancake bằng mock. Sau khi test pass, chuẩn bị checklist rollout để bật webhook thật một cách an toàn.

Test không gọi Pancake thật, không cần external service và chạy bằng `pytest -q` theo guideline repo.

## Phạm vi kiểm thử

- Endpoint Pancake webhook.
- Normalize payload Pancake.
- Persistence `Conversation` và `Message`.
- Duplicate guard.
- AI/rule path bằng mock.
- Pancake Public API send bằng mock.
- Error handling và logging an toàn.
- Admin takeover Pancake: Public API echo, admin người thật, pause guard trước/sau AI.
- Regression suite toàn repo.

## File test liên quan

- `tests/test_pancake_webhook.py`
- `tests/test_pancake_message_service.py`
- `tests/test_conversations_api.py`, nếu ảnh hưởng behavior conversation chung.
- `tests/test_facebook_webhook_forward.py`, chỉ để đảm bảo không regress Facebook nếu có chỉnh shared helper.

## Checklist

### 1. Test endpoint và payload invalid

- [x] Test body rỗng trả ignored/skip reason.
- [x] Test invalid JSON trả ignored/skip reason.
- [x] Test payload không phải object trả ignored/skip reason.
- [x] Test non-`messaging` event bị bỏ qua.
- [x] Test payload thiếu `data` không crash.
- [x] Test payload thiếu `data.message` không crash.

Kết quả mong muốn:
  Webhook an toàn với request xấu hoặc event không thuộc scope.

### 2. Test normalize payload

- [x] Test payload `messaging` + `INBOX` đầy đủ normalize đúng.
- [x] Test `page_id` fallback từ `data.message.page_id`.
- [x] Test `pancake_conversation_id` fallback từ `data.message.conversation_id`.
- [x] Test `sender_id` ưu tiên `page_customer_id`.
- [x] Test `sender_id` fallback `from.id`.
- [x] Test `sender_name` fallback từ conversation.
- [x] Test page/admin payload map đúng `conversation_customer_id`, `conversation_sender_id`, `message_from_admin_name`, `message_from_uid`.
- [x] Test `original_message` được ưu tiên.
- [x] Test fallback `message` được strip HTML.
- [x] Test `attachments` và `post_id` được giữ.
- [x] Test thiếu field bắt buộc trả reason rõ ràng.

Kết quả mong muốn:
  Normalize ổn định và không bị phụ thuộc một shape payload duy nhất.

### 3. Test conversation/message persistence

- [x] Test tạo conversation mới theo `sender_id`.
- [x] Test reuse conversation cũ theo `sender_id`.
- [x] Test update channel/name khi có dữ liệu mới.
- [x] Test message khách lưu đúng `role = "user"`.
- [x] Test message khách lưu đúng `content`.
- [x] Test `message_mid` được lưu.
- [x] Test meta có `page_id`, `sender_id`, `platform_sender_id`, `page_customer_id`, `pancake_conversation_id`.
- [x] Test không lưu token vào meta.

Kết quả mong muốn:
  Database có đủ dữ liệu cần cho dashboard/debug và không chứa token.

### 4. Test duplicate và skip rule

- [x] Test duplicate `message_mid` không insert message mới.
- [x] Test duplicate `message_mid` không gọi AI/rule.
- [x] Test duplicate `message_mid` không gọi Pancake send.
- [x] Test message removed bị skip nếu field Pancake có `is_removed = true`.
- [x] Test message không phải `INBOX` bị skip trong phase đầu.
- [x] Test echo/admin/page message không tạo reply loop nếu rule detect đã implement.
- [x] Test Public API echo bị bỏ qua và không pause conversation.
- [x] Test admin người thật lưu staff message và pause đúng conversation khách.

Kết quả mong muốn:
  BE không reply trùng hoặc tự reply chính message gửi ra.

### 5. Test AI/rule và Pancake send

- [x] Mock AI/rule trả reply text.
- [x] Mock conversation đang pause, assert customer message được lưu nhưng không gọi AI/rule.
- [x] Mock admin pause trong lúc AI/rule xử lý, assert không gọi Pancake send.
- [x] Assert Pancake send nhận đúng `page_id`.
- [x] Assert Pancake send nhận đúng `pancake_conversation_id`.
- [x] Assert Pancake send nhận đúng action.
- [x] Assert Pancake send nhận đúng message text.
- [x] Mock AI/rule trả rỗng, assert không gọi Pancake send.
- [x] Mock Pancake send success, assert webhook trả kết quả success/queued phù hợp.
- [x] Mock Pancake send lỗi auth/permission, assert reason rõ ràng và không retry vô hạn.
- [x] Mock Pancake send timeout/5xx, assert retry theo giới hạn nếu có retry.

Kết quả mong muốn:
  Happy path và failure path quan trọng đều được cover bằng mock.

### 6. Test logging/security

- [x] Assert response webhook không chứa token.
- [x] Assert log không chứa `PANCAKE_PAGE_ACCESS_TOKEN`.
- [x] Assert log không chứa query string token nếu URL có token.
- [x] Assert reason lỗi có đủ `message_mid` hoặc `pancake_conversation_id` để debug.
- [x] Assert raw payload nếu log/lưu được giới hạn và không chứa token.
- [x] Assert log normalized/detail có đủ `admin_name`, `uid`, `conversation_customer_id` để debug takeover.

Kết quả mong muốn:
  Rollout an toàn hơn, không lộ credential trong log hoặc response.

### 7. Regression suite

- [x] Chạy `pytest -q`.
- [x] Không chạy `pre-commit` theo guideline repo.
- [x] Nếu `pytest` không có trong PATH, chạy bằng Python/venv phù hợp và ghi rõ trong final.
- [x] Kiểm tra test Facebook webhook không regress nếu có chỉnh shared helper.
- [x] Ghi nhận warning hiện có nếu không liên quan task.

Kết quả mong muốn:
  Toàn bộ test suite pass trước khi cấu hình webhook thật.

### 8. Rollout checklist

- [ ] Deploy backend có endpoint Pancake.
- [ ] Cấu hình `PANCAKE_PAGE_ACCESS_TOKEN` trên môi trường chạy thật.
- [ ] Đăng ký webhook URL HTTPS `/api/v1/pancake/webhook` trong Pancake.
- [ ] Gửi một message test từ kênh thật và kiểm tra log nhận webhook.
- [ ] Kiểm tra conversation/message được lưu đúng.
- [ ] Kiểm tra Pancake nhận reply đúng hội thoại.
- [ ] Theo dõi duplicate/retry/send failed trong những ngày đầu.
- [ ] Theo dõi có reply loop từ echo/admin message hay không.
- [ ] Có cách tắt nhanh flow Pancake nếu phát sinh lỗi production.

Kết quả mong muốn:
  Rollout có kiểm soát, có thể phát hiện và tắt nhanh nếu có lỗi.

## Acceptance criteria

- [x] Test endpoint invalid/skip pass.
- [x] Test normalize pass.
- [x] Test persistence pass.
- [x] Test duplicate guard pass.
- [x] Test AI/reply path pass.
- [x] Test logging/security pass.
- [x] Facebook webhook hiện tại không regress.
- [x] Pancake admin takeover không regress reply path khách thường.
- [x] `pytest -q` pass.
- [x] Rollout checklist đủ để bật webhook thật.

## Ghi chú mở

- Manual test Pancake thật không nên nằm trong CI.
- Nếu production có nhiều page/token, cần thêm test mapping token theo `page_id`.
- Nếu phát hiện Pancake gửi nhiều event cho cùng một message, ưu tiên mở rộng duplicate guard trước khi tối ưu AI/reply.
