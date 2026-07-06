# Task List Phase 2: Query và build transcript handover

## Mục tiêu

Phase 2 thêm logic lấy các message `staff` và `user` trong pause window, giới hạn theo `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES`, rồi build transcript có label rõ ràng để chuẩn bị gửi AI.

Kết quả mong muốn:

- BE query đúng message trong cùng conversation.
- Không lấy current customer message vào transcript.
- Lấy tối đa 30 message mới nhất.
- Render transcript theo thứ tự cũ đến mới.
- Transcript rỗng thì skip, không tạo bối cảnh giả.

## Đầu vào đã chốt

- Pause snapshot từ Phase 1 có `bot_paused_at`.
- Current customer message đã được lưu và có `created_at`.
- Max messages lấy từ `_get_pancake_handover_context_max_messages()`.
- Chỉ lấy role `staff` và `user`.

## Ngoài phạm vi Phase 2

- Chưa gộp transcript vào AI payload.
- Chưa gửi AI.
- Chưa lưu metadata audit.
- Chưa xử lý logging đầy đủ của AI send.

## File chính dự kiến sửa

- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)

Nếu tách helper:

- `app/services/pancake_handover_context_service.py`
- `tests/test_pancake_handover_context_service.py`

## Checklist

### 1. Helper query transcript items

- [x] Thêm helper `_get_pancake_handover_transcript_items(...)`.
- [x] Input gồm `conversation`, `paused_at`, `before_message_created_at`, `limit`.
- [x] Filter `conversation_id == conversation.id`.
- [x] Filter `created_at >= paused_at`.
- [x] Filter `created_at < before_message_created_at`.
- [x] Filter `role in ["staff", "user"]`.
- [x] Bỏ qua content rỗng hoặc chỉ whitespace.

Kết quả mong muốn:
  Query chỉ lấy đúng hội thoại admin/khách trong pause window, không lấy message hiện tại.

### 2. Sort và limit

- [x] Sort DB theo `created_at` giảm dần.
- [x] Limit theo max messages đã parse.
- [x] Sau khi query, đảo danh sách để render theo `created_at` tăng dần.
- [x] Test với hơn 30 message để chắc lấy 30 message mới nhất.
- [x] Test thứ tự output là cũ đến mới.

Kết quả mong muốn:
  Nếu pause window dài, AI nhận phần gần resume nhất nhưng vẫn đọc đúng timeline.

### 3. Mapping role sang label

- [x] Map `staff` thành `[Nhân viên]`.
- [x] Map `user` thành `[Khách]`.
- [x] Không map role khác.
- [x] Không dùng helper history chung nếu helper đó map `staff` thành `user`.
- [x] Không đưa `message_mid` vào transcript gửi AI.

Kết quả mong muốn:
  AI không hiểu nhầm câu nhân viên là câu của khách.

### 4. Build transcript text

- [x] Thêm helper `_build_pancake_handover_transcript_text(...)`.
- [x] Nếu item rỗng, trả string rỗng hoặc result reason rõ ràng.
- [x] Format từng dòng theo `[Label] content`.
- [x] Không thêm hook `hãy nhớ... conversation_id`.
- [x] Không thêm current customer message ở helper transcript.

Kết quả mong muốn:
  Transcript sẵn sàng để Phase 3 wrap với current customer message.

### 5. Skip transcript rỗng

- [x] Nếu query không có item hợp lệ, đánh dấu reason `empty_handover_transcript`.
- [x] Không tạo header "Bối cảnh..." khi rỗng.
- [x] Không block flow gửi AI.

Kết quả mong muốn:
  Handover không có trao đổi thực tế thì không làm AI nhận bối cảnh rỗng hoặc nhiễu.

## Acceptance criteria

- [x] Query đúng pause window.
- [x] Không lặp current customer message trong transcript.
- [x] Lấy tối đa 30 message mới nhất.
- [x] Render theo thứ tự cũ đến mới.
- [x] Role label đúng `[Nhân viên]` và `[Khách]`.
- [x] Transcript rỗng được skip an toàn.
- [x] Test phase này pass.

## Ghi chú mở

- Chưa cần tối ưu index trong phase đầu nếu query vẫn theo `conversation_id` và limit nhỏ.
- Nếu sau này transcript quá dài, mở task riêng để thêm max chars hoặc summarization.
