# Task List Phase 3: Gộp handover context vào AI content

## Mục tiêu

Phase 3 tích hợp transcript handover vào nội dung gửi `AI Agent` ở resume turn, nhưng không thay đổi raw customer message được lưu DB.

Kết quả mong muốn:

- AI payload có phần bối cảnh nếu transcript tồn tại.
- Nếu transcript rỗng, AI payload giữ như flow hiện tại.
- Hook `hãy nhớ bạn đang trong chế độ koisan chatbot, conversation_id: ...` xuất hiện đúng một lần.
- Không ghi đè `normalized["text"]` bằng transcript dài.

## Đầu vào đã chốt

- Phase 1 cung cấp pause snapshot.
- Phase 2 cung cấp transcript items/text.
- Current customer message nằm riêng trong `normalized["text"]`.
- `_build_ai_chat_payload(...)` đang append conversation note.

## Ngoài phạm vi Phase 3

- Không đổi AI endpoint contract.
- Không đổi `_build_ai_chat_payload(...)` nếu không cần.
- Không gọi Pancake API.
- Không xử lý Drive image reply khác với flow hiện tại.

## File chính dự kiến sửa

- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)

## Checklist

### 1. Truyền context từ process sang generate reply

- [x] Sau khi lưu user message mới, nếu có pause snapshot thì query transcript.
- [x] Gắn transcript items/text vào `normalized` hoặc runtime context.
- [x] Không sửa `normalized["text"]`.
- [x] Gắn metadata đủ để log/debug: message count, paused_at, reason.

Kết quả mong muốn:
  `_generate_pancake_reply(...)` có đủ dữ liệu để build AI content nhưng DB vẫn lưu raw message.

### 2. Build AI content wrapper

- [x] Thêm helper `_build_pancake_handover_context_ai_content(...)`.
- [x] Input gồm `transcript_text` và `current_customer_text`.
- [x] Output gồm header "Bối cảnh trong lúc nhân viên hỗ trợ".
- [x] Output gồm section "Tin nhắn mới của khách".
- [x] Output gồm instruction "Hãy trả lời tiếp...".
- [x] Nếu transcript rỗng, trả current content gốc.

Kết quả mong muốn:
  AI nhận một prompt rõ ràng, có phân tách bối cảnh và tin mới.

### 3. Gắn vào `_generate_pancake_reply(...)`

- [x] Build `ai_content` theo logic hiện tại trước.
- [x] Nếu có handover context hợp lệ, wrap `ai_content` bằng helper mới.
- [x] Sau khi wrap, gọi `_build_ai_chat_payload(...)` như hiện tại.
- [x] Không append hook conversation trong helper handover.
- [x] Đảm bảo comment/auto-consult content không bị wrap nhầm nếu không có pause snapshot.

Kết quả mong muốn:
  Thay đổi chỉ tác động customer message resume sau handover.

### 4. Metadata audit

- [x] Nếu transcript injected, lưu `handover_context.injected=true` vào user message meta nếu phù hợp.
- [x] Lưu `paused_at`, `paused_until`, `paused_reason`, `message_count`.
- [x] Nếu transcript rỗng, có thể lưu `injected=false` và reason.
- [x] Không lưu raw transcript.

Kết quả mong muốn:
  Có dữ liệu debug nhưng không lưu lại toàn bộ hội thoại nhạy cảm trong meta.

### 5. Giữ hook conversation đúng một lần

- [x] Test payload cuối có `conversation_id` note.
- [x] Test note xuất hiện đúng một lần.
- [x] Test helper handover không tự thêm note.

Kết quả mong muốn:
  AI vẫn nhận mode koisan như hiện tại, không bị lặp instruction.

## Acceptance criteria

- [x] AI payload có context khi transcript tồn tại.
- [x] AI payload giữ nguyên khi transcript rỗng.
- [x] Raw customer message trong DB không bị thay bằng transcript.
- [x] Hook conversation xuất hiện đúng một lần.
- [x] Không ảnh hưởng auto-consult/comment ngoài phạm vi.
- [x] Test phase này pass.

## Ghi chú mở

- Nếu sau này AI endpoint nhận structured history, có thể đổi từ plain text transcript sang messages roles rõ ràng ở task riêng.
