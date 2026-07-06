# Task List Phase 4: Tích hợp webhook và chốt version

## Mục tiêu

Phase 4 nối version check, versioned AI user, init và history context vào flow customer message thực tế; chỉ update version sau AI context call thành công.

Kết quả mong muốn:

- Same hoặc higher version giữ flow hiện tại nhưng dùng đúng versioned AI user.
- Older version chạy đủ B1-B4.
- Customer nhận duy nhất reply cuối cùng.

## Đầu vào đã chốt

- Phase 1 có config/model/comparator.
- Phase 2 có versioned AI user/init sequence.
- Phase 3 có text-history helper.
- Version upgrade chạy trước normal `_ensure_sender_initialized(...)`.

## Ngoài phạm vi Phase 4

- Chưa hoàn thiện distributed locking nếu cần hạ tầng ngoài.
- Chưa rollout production.
- Không thay đổi business instruction trong `SKILL.md`.

## File chính dự kiến sửa

- `app/api/v1/facebook_webhook.py`
- `app/api/v1/pancake_webhook.py`
- `app/services/ai_version_context_service.py`
- `tests/test_facebook_webhook_forward.py`
- `tests/test_pancake_webhook.py`

## Checklist

### 1. Guard và vị trí version check

- [x] Chỉ customer message eligible mới check.
- [x] Chạy sau duplicate/dangerous keyword/pause guard.
- [x] Chạy trước normal init.
- [x] Admin/bot echo không chạy migration.
- [x] Unsupported content không chốt version.

Kết quả mong muốn:
  Version upgrade chỉ xảy ra đúng lúc backend thực sự chuẩn bị gọi AI cho khách.

### 2. Facebook integration

- [x] Tích hợp vào `_run_ai_forward_and_reply(...)`.
- [x] Build versioned AI user trước init/AI call.
- [x] Current customer message truyền riêng, không lặp history.
- [x] Xác định và test behavior message trong admin pause.
- [x] Init response không qua Facebook send API.
- [x] Normal reply vẫn save user/bot như hiện tại hoặc theo persist-before-AI contract mới.

Kết quả mong muốn:
  Facebook giữ behavior gửi reply nhưng AI được đưa sang session version mới và nhận context khi version cũ.

### 3. Pancake integration

- [x] Tích hợp sau user message save/pause guard.
- [x] Build versioned AI user trước init/AI call.
- [x] Sender buffer dùng merged current content.
- [x] Exclude toàn bộ user message IDs trong batch khỏi history.
- [x] Auto-consult/comment flow có quyết định scope rõ.
- [x] Init response được xử lý nội bộ.

Kết quả mong muốn:
  Một batch customer messages chỉ tạo một context call và một reply.

### 4. Gửi context/current message

- [x] Chỉ chạy sau init success.
- [x] History rỗng vẫn gửi current message.
- [x] Await AI response hợp lệ.
- [x] Không save init response làm bot message.
- [x] B3 dùng cùng versioned AI user với init.

Kết quả mong muốn:
  AI trả lời dựa trên instruction mới và history text.

### 5. Chốt version

- [x] Set `conversation.version=system_version` sau B3 success.
- [x] Save trước outbound channel reply.
- [x] Update `updated_at`.
- [x] B1/B2/B3 failure không update version.
- [x] Save version failure có result/log rõ.

Kết quả mong muốn:
  DB chỉ xác nhận version sau khi AI đã nhận context thành công.

## Acceptance criteria

- [x] Older version chạy đúng call order.
- [x] Same hoặc higher version dùng đúng versioned AI user.
- [x] Version update đúng thời điểm.
- [x] Facebook/Pancake chỉ gửi reply cuối ra khách.

## Ghi chú mở

- Auto-consult/comment đi qua `_generate_pancake_reply(...)`; version upgrade chỉ chạy khi flow đã đủ điều kiện gọi AI cho customer-facing reply.
- Nếu Facebook cần lưu customer message trong pause để history đầy đủ, thay đổi persist order phải có dedupe test riêng.
