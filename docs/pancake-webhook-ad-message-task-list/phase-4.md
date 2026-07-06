# Task List Phase 4: Gọi AI và gửi reply Pancake

## Mục tiêu

Phase 4 chạy phần hành vi chính: kiểm tra duplicate/pause, gọi AI bằng prompt lookbook, xử lý reply text/Drive image theo flow hiện có, và gửi câu trả lời vào đúng Pancake conversation.

Kết quả mong muốn:

- Mỗi trigger hợp lệ chỉ gọi AI một lần.
- Không gọi AI hoặc gửi reply khi admin đang chăm sóc.
- Reply gửi đúng `page_id` và `pancake_conversation_id`.
- Bot message lưu được kết quả gửi và metadata auto consult.

## Đầu vào đã chốt

- User message tổng hợp từ Phase 3.
- Prompt đã có dạng `tư vấn mẫu {product_codes_csv} và gửi ảnh lookbook`.
- Flow Drive image hiện có vẫn xử lý nếu AI trả Drive link.

## Ngoài phạm vi Phase 4

- Không thay đổi logic AI Agent.
- Không thay đổi Google Drive image flow ngoài việc reuse.
- Không support message type ngoài `INBOX` trong phase đầu.

## File chính dự kiến sửa

- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [app/services/pancake_message_service.py](../../app/services/pancake_message_service.py)
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)

## Checklist

### 1. Duplicate và pause guard

- [x] Check duplicate theo `trigger_type + trigger_message_mid`.
- [x] Nếu duplicate, return `duplicate_auto_consult` trước khi gọi AI.
- [x] Dùng inflight guard để tránh webhook đồng thời gọi AI hai lần.
- [x] Resume pause nếu đã hết hạn.
- [x] Nếu conversation đang pause, không gọi AI, return `conversation_paused_by_admin`.
- [x] Reload conversation và check pause lần hai trước khi gửi reply.
- [x] Nếu pause xuất hiện trước khi gửi, return `conversation_paused_before_send`.

Kết quả mong muốn:
  Không spam khách và không đè admin thật.

### 2. Gọi AI

- [x] Init AI nếu conversation chưa initialized, theo flow hiện có.
- [x] Gọi AI với `user=customer_id`, không phải `page_id`.
- [x] Gửi `content` là prompt lookbook.
- [x] Reuse retry/backoff AI hiện có.
- [x] Nếu AI call lỗi, không gửi Pancake reply.
- [x] Nếu AI response rỗng, không gửi Pancake reply.
- [x] Log AI start/ok/failed với `trigger_type`, `trigger_message_mid`, `product_codes`.

Kết quả mong muốn:
  AI nhận đúng session và prompt, lỗi AI không biến thành tin nhắn rỗng cho khách.

### 3. Chuẩn bị và gửi reply

- [x] Tách Drive link khỏi AI text theo flow hiện có.
- [x] Reuse flow cache/download/upload/send image nếu AI trả Drive link.
- [x] Gửi text reply trước bằng `send_pancake_reply`.
- [x] Dùng `page_id` từ trigger.
- [x] Dùng `pancake_conversation_id` từ trigger.
- [x] Dùng `action=reply_inbox`.
- [x] Không gửi nếu message type không phải `INBOX`, return `unsupported_reply_action`.
- [x] Không gửi image message nếu `content_ids` rỗng.
- [x] Log send ok/failed không kèm token.

Kết quả mong muốn:
  Khách nhận reply trong đúng conversation hiện tại.

### 4. Lưu bot message

- [x] Lưu bot message với `meta.source=pancake_auto_consult`.
- [x] Lưu `reply_to_message_mid=trigger_message_mid`.
- [x] Lưu `auto_consult.trigger_type`.
- [x] Lưu `auto_consult.product_codes`.
- [x] Lưu `ad_id`, `post_id`, `comment_id` nếu có.
- [x] Lưu send result rút gọn.
- [x] Lưu Drive image metadata nếu flow ảnh chạy.
- [x] Không lưu token.

Kết quả mong muốn:
  Audit đủ biết bot reply đến từ trigger nào và đã gửi Pancake thành công hay thất bại.

## Acceptance criteria

- [x] Test duplicate trigger không gọi AI lần hai.
- [x] Test paused conversation không gọi AI/send.
- [x] Test pause xuất hiện trước send thì không gửi.
- [x] Test AI success gửi đúng Pancake conversation.
- [x] Test AI empty không gửi Pancake.
- [x] Test bot message lưu metadata auto consult.
- [x] Test Drive link reply vẫn đi qua flow ảnh hiện có.

## Ghi chú mở

- Nếu reply lookbook cần gửi ảnh bắt buộc, behavior khi AI không trả Drive link nên do business quyết định ở phase sau.
