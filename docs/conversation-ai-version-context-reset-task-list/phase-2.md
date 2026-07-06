# Task List Phase 2: AI session mới theo version và init AI

## Mục tiêu

Phase 2 implement hai bước đầu của version upgrade: chuyển sang AI session mới bằng versioned AI user, sau đó init lại bằng `FB_AI_INIT_MESSAGE`.

Kết quả mong muốn:

- `fb_ai_initialized=false` được persist trước khi dùng session mới.
- Versioned AI user được build nhất quán.
- Init hoàn tất trước khi caller được phép gửi context.
- Response init là kết quả nội bộ của bước khởi tạo.

## Đầu vào đã chốt

- Version helper Phase 1 xác định conversation `older`.
- `_post_ai_chat_with_retry(...)` vẫn là transport AI.
- `_ensure_sender_initialized(...)` vẫn quản lý init flag.

## Ngoài phạm vi Phase 2

- Chưa query history.
- Chưa gửi customer message có context.
- Chưa update conversation version.
- Chưa tích hợp đầy đủ Facebook/Pancake webhook.

## File chính dự kiến sửa

- `app/api/v1/facebook_webhook.py`
- `app/services/ai_version_context_service.py` nếu tách orchestration
- `tests/test_facebook_webhook_forward.py`
- `tests/test_ai_version_context_service.py`

## Checklist

### 1. Versioned AI user helper

- [x] Thêm helper `build_versioned_ai_user(sender_id, version)`.
- [x] Format mặc định `<sender_id>:v<version>`.
- [x] Validate/normalize version trước khi build.
- [x] Test output với `sender_id=e8b3...`, `version=1.1`.
- [x] Không thay đổi format tùy tiện ở từng webhook.

Kết quả mong muốn:
  Mọi AI call của cùng conversation/version đi vào cùng OpenClaw session mới.

### 2. Persist init state

- [x] Set `fb_ai_initialized=false`.
- [x] Clear `fb_ai_initialized_at`.
- [x] Update timestamp phù hợp.
- [x] Await save trước khi init session mới.
- [x] Save lỗi thì không gọi AI.

Kết quả mong muốn:
  DB phản ánh session mới cần init lại trước khi xử lý customer message.

### 3. Init lại

- [x] Gọi `_ensure_sender_initialized(...)` với versioned AI user.
- [x] Await init success.
- [x] Chỉ init success mới set flag true/time.
- [x] Init failure giữ version cũ.

Kết quả mong muốn:
  AI session mới đã đọc instruction hiện tại trước khi nhận context.

## Acceptance criteria

- [x] Thứ tự save false → build AI user mới → init được test.
- [x] Failure trước init không cho chạy context.
- [x] Failure ở init không cho chạy context.
- [x] Response init được xử lý nội bộ.

## Ghi chú mở

- Cần quyết định nếu `conversation.version` cao hơn env thì dùng versioned AI user theo DB version hay fallback legacy; proposal chọn dùng DB version nếu hợp lệ và log warning.
- Helper phải đủ tập trung để sau này nếu đổi format sang `conversation_id:v<version>` chỉ sửa một nơi.
