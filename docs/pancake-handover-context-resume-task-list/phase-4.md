# Task List Phase 4: Logging, fallback và an toàn vận hành

## Mục tiêu

Phase 4 bổ sung logging và fallback để flow handover context an toàn khi query DB lỗi, transcript rỗng, env sai hoặc conversation vẫn đang pause.

Kết quả mong muốn:

- Có log đủ để biết resume context được injected hay skipped.
- Không log raw transcript.
- Lỗi query transcript không block AI.
- Conversation còn pause vẫn không gọi AI.
- Hook conversation không bị lặp.

## Đầu vào đã chốt

- Phase 1 có config và pause snapshot.
- Phase 2 có query/build transcript.
- Phase 3 có AI content wrapper.

## Ngoài phạm vi Phase 4

- Không thêm alert/monitoring external.
- Không thêm dashboard.
- Không đổi schema API.
- Không thêm lock chống race tuyệt đối nếu chưa có bằng chứng cần thiết.

## File chính dự kiến sửa

- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)

## Checklist

### 1. Logging resume context

- [x] Log `PANCAKE_HANDOVER_CONTEXT_RESUME_DETECTED` khi có pause snapshot hết hạn.
- [x] Log `conversation_id`, `page_id`, `pancake_conversation_id`.
- [x] Log `message_mid`, `sender_id`.
- [x] Log `paused_at`, `paused_until`, `paused_reason`.
- [x] Không log nội dung transcript.

Kết quả mong muốn:
  Có thể xác định khi nào BE cố inject context mà không lộ dữ liệu cá nhân.

### 2. Logging fetch transcript

- [x] Log `PANCAKE_HANDOVER_CONTEXT_FETCH_START`.
- [x] Log `PANCAKE_HANDOVER_CONTEXT_FETCH_OK` với `message_count` và `max_messages`.
- [x] Log `PANCAKE_HANDOVER_CONTEXT_FETCH_FAILED` nếu query lỗi.
- [x] Không log message content.

Kết quả mong muốn:
  Debug được lỗi ở bước query transcript.

### 3. Logging injected/skipped

- [x] Log `PANCAKE_HANDOVER_CONTEXT_INJECTED` khi context được wrap vào AI content.
- [x] Log `PANCAKE_HANDOVER_CONTEXT_SKIPPED` khi transcript rỗng hoặc thiếu snapshot.
- [x] Reason cần rõ: `empty_handover_transcript`, `missing_pause_snapshot`, `conversation_still_paused`.
- [x] Log `message_count`.

Kết quả mong muốn:
  Có thể phân biệt handover rỗng với lỗi query hoặc conversation vẫn pause.

### 4. Fallback an toàn

- [x] Nếu query transcript lỗi, fallback về AI content gốc.
- [x] Nếu transcript rỗng, fallback về AI content gốc.
- [x] Nếu env sai format, fallback max messages `30`.
- [x] Nếu conversation vẫn pause sau reload, không gọi AI.
- [x] Nếu hook conversation bị lặp trong test, sửa để helper handover không append hook.

Kết quả mong muốn:
  Tính năng mới không làm hỏng flow chat hiện tại.

### 5. Không log dữ liệu nhạy cảm

- [x] Không log full transcript.
- [x] Không log số điện thoại/địa chỉ raw từ transcript.
- [x] Không log Pancake token.
- [x] Không log URL có token.

Kết quả mong muốn:
  Production log đủ debug mà không lộ PII hoặc credential.

## Acceptance criteria

- [x] Có log injected/skipped/fetch failed rõ ràng.
- [x] Query lỗi không block AI.
- [x] Transcript rỗng không tạo bối cảnh giả.
- [x] Conversation vẫn pause không gọi AI.
- [x] Raw transcript không xuất hiện trong log.
- [x] Test phase này pass.

## Ghi chú mở

- Sau rollout, nếu log cho thấy nhiều `fetch_failed`, cần kiểm tra query/index hoặc lỗi Beanie.
- Nếu log cho thấy nhiều `empty_handover_transcript`, có thể do pause được tạo bởi AI handover nhưng nhân viên chưa vào support.
