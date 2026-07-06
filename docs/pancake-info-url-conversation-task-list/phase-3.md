# Task List Phase 3: Dữ liệu cũ, logging và fallback

## Mục tiêu

Phase 3 đảm bảo field mới không làm hỏng dữ liệu cũ, logging không lộ dữ liệu nhạy cảm, và các trường hợp thiếu dữ liệu URL có fallback rõ ràng.

Kết quả mong muốn:

- Conversation cũ không có `pancake_info_url` vẫn hoạt động bình thường.
- Message mới của conversation cũ không tự backfill field.
- Log không chứa token hoặc auth data.
- Nếu thiếu input build URL, flow không crash ngoài validate hiện tại.

## Đầu vào đã chốt

- `pancake_info_url` optional.
- Không migration bắt buộc.
- Không backfill trong request webhook.
- Nếu cần backfill, làm bằng script riêng.

## Ngoài phạm vi Phase 3

- Không viết script backfill thật.
- Không thêm monitoring dashboard.
- Không đổi retention/logging infra.
- Không thêm UI hiển thị link.

## File chính dự kiến sửa

- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)
- [tests/test_conversations_api.py](../../tests/test_conversations_api.py)

## Checklist

### 1. Tương thích dữ liệu cũ

- [x] Test load conversation không có field `pancake_info_url`.
- [x] Test list conversation không có field này.
- [x] Test detail conversation không có field này.
- [x] Test update conversation cũ không yêu cầu field này.
- [x] Đảm bảo default model là `None`.

Kết quả mong muốn:
  Deploy field mới không yêu cầu migration đồng bộ trước.

### 2. Không auto-backfill

- [x] Test conversation đã tồn tại và `pancake_info_url=None` không bị set khi có message mới.
- [x] Test conversation đã tồn tại và có URL cũ không bị overwrite khi có message mới.
- [x] Ghi chú backfill phải là script riêng nếu sau này cần.

Kết quả mong muốn:
  Rule tạo một lần lúc create được giữ đúng.

### 3. Logging và fallback

- [x] Log tạo conversation không in token.
- [x] Log lỗi build URL nếu cần chỉ gồm `page_id`, `pancake_conversation_id`, `sender_id` rút gọn.
- [x] Không log raw auth header.
- [x] Không log Pancake access token.
- [x] Nếu helper trả `None`, không crash ngoài behavior validate hiện tại.

Kết quả mong muốn:
  Thay đổi đủ quan sát được nhưng không làm tăng rủi ro bảo mật.

## Acceptance criteria

- [x] Conversation cũ vẫn hoạt động bình thường.
- [x] Message mới không tự backfill conversation cũ.
- [x] URL hiện có không bị overwrite.
- [x] Log không chứa token/auth data.
- [x] Fallback thiếu input đã được test.

## Ghi chú mở

- Nếu cần audit/backfill sau này, script nên chỉ update document thiếu field hoặc field `null`, không overwrite string URL đã có.
