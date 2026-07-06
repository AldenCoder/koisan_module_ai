# Task List Phase 1: Cấu hình và pause snapshot

## Mục tiêu

Phase 1 bổ sung cấu hình `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES` và điều chỉnh flow resume pause để giữ được pause snapshot trước khi clear các field `bot_paused_*`.

Kết quả mong muốn:

- Config đọc được `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES`.
- Default là `30`.
- Env sai format không làm crash webhook.
- Khi pause hết hạn, BE lấy được snapshot gồm `bot_paused_at`, `bot_paused_until`, `bot_paused_reason`, `bot_paused_by`.
- Sau khi resume, các field pause vẫn được clear về `None` như behavior hiện tại.

## Đầu vào đã chốt

- Env duy nhất phase đầu là `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES=30`.
- Không thêm feature flag.
- Không thêm max chars.
- Không thêm field boolean riêng trên conversation.
- Pause snapshot phải được lấy trước khi clear pause fields.

## Ngoài phạm vi Phase 1

- Chưa query transcript.
- Chưa build AI content handover.
- Chưa gộp vào `_generate_pancake_reply`.
- Chưa thêm logging chi tiết cho transcript.
- Chưa thêm test end-to-end AI payload.

## File chính dự kiến sửa

- [app/core/config.py](../../app/core/config.py)
- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)

## Checklist

### 1. Thêm config

- [x] Thêm `pancake_handover_context_max_messages: int = 30` vào settings.
- [x] Đảm bảo tên env mapping đúng theo convention hiện tại.
- [x] Không thêm env `PANCAKE_HANDOVER_CONTEXT_ENABLED`.
- [x] Không thêm env `PANCAKE_HANDOVER_CONTEXT_MAX_CHARS`.

Kết quả mong muốn:
  Backend đọc được số lượng message tối đa từ env, mặc định 30.

### 2. Helper parse/clamp max messages

- [x] Thêm helper `_get_pancake_handover_context_max_messages()`.
- [x] Nếu value rỗng hoặc sai format, fallback `30`.
- [x] Nếu value nhỏ hơn `1`, clamp về `1`.
- [x] Nếu value quá lớn, clamp mức an toàn, ví dụ `50`.
- [x] Không log raw env nếu không cần thiết.

Kết quả mong muốn:
  Config sai không làm webhook lỗi và không tạo payload quá lớn ngoài ý muốn.

### 3. Pause snapshot

- [x] Tạo helper resume mới hoặc chỉnh helper hiện tại để trả pause snapshot.
- [x] Snapshot chứa `resumed`, `bot_paused_at`, `bot_paused_until`, `bot_paused_reason`, `bot_paused_by`.
- [x] Snapshot chỉ `resumed=true` khi pause đã hết hạn.
- [x] Nếu chưa pause hoặc chưa hết hạn, trả kết quả rõ ràng.
- [x] Giữ behavior clear pause fields về `None` khi resume.

Kết quả mong muốn:
  Flow sau resume vẫn biết pause window bắt đầu từ đâu để phase 2 query transcript.

### 4. Tích hợp vào `_process_normalized_message`

- [x] Chụp pause snapshot trước khi logic clear mất field pause.
- [x] Gắn snapshot vào runtime context hoặc `normalized`.
- [x] Không thay đổi behavior khi conversation vẫn đang pause.
- [x] Không gọi AI nếu pause vẫn active.
- [x] Không ảnh hưởng duplicate/in-flight guard hiện có.

Kết quả mong muốn:
  Customer message sau pause có đủ dữ liệu để build handover context ở các phase sau.

## Acceptance criteria

- [x] `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES` default là `30`.
- [x] Env sai format fallback `30`.
- [x] Pause snapshot lấy được trước khi clear fields.
- [x] Pause fields vẫn clear về `None` sau resume.
- [x] Conversation đang pause vẫn không gọi AI.
- [x] Test phase này pass.

## Ghi chú mở

- Nếu helper hiện tại đang được nhiều test phụ thuộc return type bool, ưu tiên tạo helper mới để tránh phá contract cũ.
- Snapshot có thể nằm trong `normalized["handover_resume_context"]` nhưng không nên ghi vào DB ở phase này.
