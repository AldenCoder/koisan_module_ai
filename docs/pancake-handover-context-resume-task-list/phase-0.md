# Task List Phase 0: Chốt giải pháp handover context resume

## Mục tiêu

Phase 0 chốt phạm vi và contract tổng thể cho việc bổ sung context handover khi Pancake bot resume sau admin takeover.

Phase này chỉ chốt giải pháp và ranh giới trách nhiệm. Chưa sửa code, chưa thêm config, chưa thêm test.

## Quyết định cần chốt

- Chỉ inject handover context ở lượt customer message đầu tiên sau khi `bot_paused_until` đã hết hạn.
- Dùng các field pause hiện có làm tín hiệu resume:
  - `bot_paused_at`
  - `bot_paused_until`
  - `bot_paused_reason`
  - `bot_paused_by`
- Không thêm cờ boolean riêng kiểu `handover_context_injected` trên conversation.
- Giới hạn transcript bằng `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES=30`.
- Nếu pause window có hơn 30 message hợp lệ, lấy 30 message mới nhất.
- Sau khi chọn 30 message mới nhất, render transcript theo thứ tự cũ đến mới.
- Chỉ lấy role `staff` và `user`.
- Không lấy role `bot`, `system`, automation hoặc message content rỗng.
- Không lấy current customer message vào transcript.
- Nếu handover transcript rỗng, không gửi phần bối cảnh sang AI.
- Hook `hãy nhớ bạn đang trong chế độ koisan chatbot, conversation_id: ...` vẫn do `_build_ai_chat_payload(...)` append.
- Không gọi Pancake API để lấy handover history.
- Không log raw transcript.

## Ngoài phạm vi Phase 0

- Chưa thêm env/config.
- Chưa sửa helper resume pause.
- Chưa query message trong pause window.
- Chưa build transcript.
- Chưa gộp transcript vào AI content.
- Chưa thêm metadata audit.
- Chưa thêm test.
- Chưa tạo migration/backfill dữ liệu cũ.

## File tài liệu liên quan

- [docs/pancake-handover-context-resume.md](../pancake-handover-context-resume.md)
- [docs/pancake-handover-context-resume-task-list/phase-1.md](phase-1.md)
- [docs/pancake-handover-context-resume-task-list/phase-2.md](phase-2.md)
- [docs/pancake-handover-context-resume-task-list/phase-3.md](phase-3.md)
- [docs/pancake-handover-context-resume-task-list/phase-4.md](phase-4.md)
- [docs/pancake-handover-context-resume-task-list/phase-5.md](phase-5.md)

## Checklist

### 1. Chốt thời điểm inject context

- [x] Xác nhận chỉ inject khi customer message đến sau khi pause đã hết hạn.
- [x] Xác nhận không inject trong lúc conversation vẫn đang pause.
- [x] Xác nhận không inject ở các lượt sau khi pause fields đã clear.
- [x] Xác nhận không tự bật bot khi admin vẫn đang support.

Kết quả mong muốn:
  Bot chỉ dùng handover context ở resume turn, không chen vào lúc admin đang xử lý.

### 2. Chốt giới hạn transcript

- [x] Xác nhận env là `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES`.
- [x] Xác nhận giá trị rollout là `30`.
- [x] Xác nhận nếu nhiều hơn 30 message thì lấy 30 message mới nhất.
- [x] Xác nhận sau khi limit thì render theo timeline cũ đến mới.
- [x] Xác nhận không thêm env max chars trong phase đầu.

Kết quả mong muốn:
  Context đủ rộng cho đoạn admin support phổ biến nhưng không gửi lịch sử không giới hạn.

### 3. Chốt nguồn dữ liệu

- [x] Xác nhận chỉ dùng DB `messages` đã lưu.
- [x] Xác nhận không gọi Pancake Conversation Messages API.
- [x] Xác nhận chỉ lấy role `staff` và `user`.
- [x] Xác nhận bỏ qua content rỗng.
- [x] Xác nhận không lấy current customer message vào transcript.

Kết quả mong muốn:
  Flow nhanh, ít phụ thuộc external API, và không lặp tin nhắn mới của khách.

### 4. Chốt format gửi AI

- [x] Xác nhận label `[Nhân viên]` cho role `staff`.
- [x] Xác nhận label `[Khách]` cho role `user`.
- [x] Xác nhận current message nằm ở phần `Tin nhắn mới của khách`.
- [x] Xác nhận prompt yêu cầu AI trả lời tiếp và không hỏi lại thông tin đã có.
- [x] Xác nhận `_build_ai_chat_payload(...)` vẫn là nơi append hook conversation.

Kết quả mong muốn:
  AI phân biệt rõ bối cảnh cũ và tin nhắn mới, không hiểu nhầm câu admin là câu khách.

## Acceptance criteria

- [x] Proposal chính mô tả rõ giới hạn `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES=30`.
- [x] Proposal chính mô tả rõ lấy 30 message mới nhất, render cũ đến mới.
- [x] Proposal chính mô tả rõ handover rỗng thì không gửi context.
- [x] Proposal chính mô tả rõ hook conversation vẫn giữ như hiện tại.
- [x] Proposal chính mô tả rõ không cần cờ boolean riêng trên conversation.

## Ghi chú mở

- Nếu sau rollout xuất hiện race condition ở resume turn, mở task riêng để thêm marker theo `paused_at` hoặc lock theo conversation.
- Nếu AI vẫn hỏi lại thông tin đã có, ưu tiên chỉnh format transcript trước khi tăng giới hạn message.
