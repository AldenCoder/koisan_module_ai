# Task List Phase 3: Tích hợp update conversation status

## Mục tiêu

Phase 3 tích hợp detector vào luồng Facebook webhook. Khi text trả lời từ Brain/AI Agent match handover, BE update conversation hiện tại sang `status = "handover"` theo `conversation_id`.

Luồng gửi tin nhắn Facebook cho khách phải giữ như hiện tại. Update status là side effect nội bộ, không làm fail reply Facebook nếu gặp lỗi.

## Phạm vi thay đổi

- Luồng `_run_ai_forward_and_reply` hoặc vị trí tương đương sau khi có text trả lời từ Brain/AI Agent.
- Gọi detector handover.
- Gọi service/API update conversation status.
- Logging rút gọn.
- Test webhook path có match/không match/error.

## File dự kiến thay đổi

- [app/api/v1/facebook_webhook.py](../../app/api/v1/facebook_webhook.py)
- [app/services/conversation_service.py](../../app/services/conversation_service.py)
- [tests/test_facebook_webhook_forward.py](../../tests/test_facebook_webhook_forward.py)

Nếu detector tách service riêng:

- [app/services/facebook_handover_detection_service.py](../../app/services/facebook_handover_detection_service.py)
- [tests/test_facebook_handover_detection_service.py](../../tests/test_facebook_handover_detection_service.py)

## Checklist

### 1. Xác định điểm tích hợp

- [x] Tìm đoạn BE đã có `assistant_message` từ `_extract_text_from_ai_response`.
- [x] Tìm đoạn BE đã có `prepared_reply.text` sau `_prepare_facebook_reply_from_ai_response`.
- [x] Chọn text cuối cùng dùng để gửi khách làm input detector.
- [x] Đảm bảo tại điểm đó đang có `conversation.id`.
- [x] Không gọi detector trước khi có response AI.

Kết quả mong muốn:
  Detector chạy đúng trên text mà khách dự kiến nhận, không chạy trên tin nhắn khách.

### 2. Gọi detector

- [x] Gọi detector sau khi có text trả lời cuối cùng.
- [x] Nếu `detected = false`, giữ nguyên flow hiện tại.
- [x] Nếu `detected = true`, chuẩn bị update `status = "handover"`.
- [x] Log `conversation_id`, `detected`, `matched_pattern` rút gọn.
- [x] Không log token hoặc payload auth.

Kết quả mong muốn:
  Handover match được nhận diện rõ nhưng không thay đổi flow khi không match.

### 3. Update conversation status

- [x] Lấy `conversation_id` từ conversation hiện tại.
- [x] Nếu thiếu `conversation_id`, log `handover_missing_conversation_id` và bỏ qua update.
- [x] Gọi service update conversation với `status=ConversationStatus.HANDOVER`.
- [x] Nếu dùng HTTP API, gọi `PATCH /api/v1/conversations/{conversation_id}` với `{"status": "handover"}`.
- [x] Nếu conversation đã là `handover`, xem là thành công/no-op.
- [x] Update `updated_at` theo behavior hiện có của service.

Kết quả mong muốn:
  Conversation match handover được đánh dấu bằng field `status` hiện có.

### 4. Giữ behavior Facebook reply

- [x] Vẫn gửi text hiện tại cho khách khi match handover.
- [x] Không pause bot.
- [x] Không set `bot_paused_at`.
- [x] Không set `bot_paused_until`.
- [x] Không set `bot_paused_reason`.
- [x] Không set `bot_paused_by`.
- [x] Nếu update status lỗi, không làm fail reply Facebook.
- [x] Nếu Facebook send lỗi, giữ behavior lỗi hiện tại của webhook.

Kết quả mong muốn:
  Task chỉ thêm status side effect, không thay đổi cam kết gửi reply hiện tại.

### 5. Test tích hợp webhook

- [x] Test AI response không match: không gọi update conversation status.
- [x] Test AI response match: gọi update status `handover`.
- [x] Test conversation đang `handover`: không fail.
- [x] Test update status raise exception: reply Facebook vẫn không bị fail do lỗi update.
- [x] Test thiếu conversation id hoặc conversation missing: không crash.
- [x] Test khách hỏi tiếp sau status handover vẫn đi qua flow gọi Brain/AI Agent nếu không bị logic pause khác chặn.

Kết quả mong muốn:
  Integration test cover cả happy path và failure path quan trọng.

## Acceptance criteria

- [x] Webhook gọi detector sau khi có text trả lời từ Brain/AI Agent.
- [x] Không match thì không update status.
- [x] Match thì update đúng conversation hiện tại thành `handover`.
- [x] Update status lỗi không làm fail reply Facebook.
- [x] Không set field pause.
- [x] Test tích hợp pass.
- [x] `pytest -q` pass.

## Ghi chú mở

- Tài liệu chính nói "call API update conversation_id"; nếu implementation chạy cùng process, gọi service nội bộ vẫn ổn nếu behavior tương đương API CRUD.
- Nếu muốn audit match pattern lâu dài, nên làm task riêng thay vì nhét vào field status.
