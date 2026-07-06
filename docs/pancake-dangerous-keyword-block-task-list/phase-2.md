# Task List Phase 2: Gắn dangerous keyword block vào Pancake webhook

## Mục tiêu

Phase 2 gắn service dangerous keyword vào `_process_normalized_message` của Pancake webhook. Block phải chạy đúng vị trí: sau khi phân loại message là tin nhắn khách hàng cần xử lý, nhưng trước duplicate DB check, trước tạo/lấy conversation, trước lưu user message, trước gọi AI và trước mọi call Pancake Public API.

Kết quả mong muốn:

- Message khách hàng chứa keyword bị ignored sớm.
- Message bị block không tạo side effect DB/API.
- Message không match tiếp tục flow hiện tại.
- Bot echo/admin/non-INBOX không bị áp dụng sai lớp chặn.

## Đầu vào đã chốt

- Phase 1 đã có service check dangerous keyword.
- `normalize_pancake_payload` trả `text`, `page_id`, `sender_id`, `message_mid`, `pancake_conversation_id`.
- `_process_normalized_message` đã có logic phân loại customer/admin/bot echo.
- Reason block public/internal là `pancake_dangerous_keyword_blocked`.

## Ngoài phạm vi Phase 2

- Không đổi rule duplicate hiện tại.
- Không đổi admin takeover hiện tại.
- Không đổi bot echo guard hiện tại.
- Không đổi Drive image reply.
- Không đổi AI prompt/response.
- Không lưu audit record riêng.

## File chính dự kiến sửa

- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [app/services/dangerous_keyword_service.py](../../app/services/dangerous_keyword_service.py)
- `tests/test_pancake_webhook_dangerous_keyword_block.py`
- Hoặc bổ sung test vào [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)

## Checklist

### 1. Xác định đúng đối tượng áp dụng

- [x] Gọi block chỉ cho `PANCAKE_MESSAGE_CUSTOMER`.
- [x] Gọi block chỉ cho message type `INBOX`.
- [x] Không gọi block cho bot echo.
- [x] Không gọi block cho admin message.
- [x] Không gọi block cho non-INBOX message.
- [x] Nếu text rỗng, giữ behavior hiện tại.

Kết quả mong muốn:
  Lớp chặn chỉ áp dụng cho text khách hàng mà backend định gửi sang AI.

### 2. Đặt block trước mọi side effect

- [x] Block chạy trước `_is_duplicate_pancake_message`.
- [x] Block chạy trước `_try_mark_pancake_message_processing`.
- [x] Block chạy trước `_get_or_create_pancake_conversation`.
- [x] Block chạy trước `_save_pancake_user_message`.
- [x] Block chạy trước `_generate_pancake_reply`.
- [x] Block chạy trước `_ensure_sender_initialized`.
- [x] Block chạy trước `_post_ai_chat_with_retry`.
- [x] Block chạy trước `send_pancake_reply`.
- [x] Block chạy trước `_send_pancake_drive_images`.

Kết quả mong muốn:
  Message bị block không chạm DB và không rời backend sang AI/Pancake.

### 3. Return object khi bị block

- [x] Return `status="ignored"`.
- [x] Return `ok=False`.
- [x] Return `reason="pancake_dangerous_keyword_blocked"`.
- [x] Return `message_kind="customer_message"`.
- [x] Return `message_mid` nếu có.
- [x] Return `page_id` nếu có.
- [x] Return `pancake_conversation_id` nếu có.
- [x] Không return `reply_text`.
- [x] Không return `message_id`.
- [x] Không return `bot_message_id`.
- [x] Không return internal `conversation_id` nếu conversation chưa tạo/lấy.
- [x] Không return full text khách hàng.

Kết quả mong muốn:
  Response đủ trace metadata nhưng không chứa nội dung bị chặn.

### 4. Giữ nguyên no-match flow

- [x] Nếu không match keyword, duplicate guard vẫn chạy như hiện tại.
- [x] Nếu không match keyword, conversation vẫn được tạo/lấy như hiện tại.
- [x] Nếu không match keyword, user message vẫn được lưu như hiện tại.
- [x] Nếu không match keyword, AI vẫn được gọi như hiện tại.
- [x] Nếu không match keyword, Pancake reply vẫn gửi như hiện tại.
- [x] Nếu không match keyword, Drive image reply vẫn hoạt động như hiện tại.

Kết quả mong muốn:
  Lớp chặn không tạo regression cho conversation hợp lệ.

### 5. Fail closed khi service lỗi

- [x] Nếu keyword file không load được, customer message bị ignored.
- [x] Reason lỗi load keyword rõ ràng trong internal result.
- [x] Không gọi AI khi service lỗi.
- [x] Không lưu user message khi service lỗi.
- [x] Không gửi Pancake reply khi service lỗi.

Kết quả mong muốn:
  Khi lớp bảo vệ lỗi, backend dừng thay vì gửi nội dung sang AI.

## Acceptance criteria

- [x] Dangerous keyword block được gọi trong `_process_normalized_message`.
- [x] Block chỉ áp dụng cho customer INBOX message.
- [x] Message match keyword trả ignored và không có side effect DB/API.
- [x] Message không match giữ nguyên flow hiện tại.
- [x] Fail-load keyword file không gọi AI.
- [x] Webhook tests cho Phase 2 pass.

## Ghi chú mở

- Vì message bị block không lưu DB, duplicate delivery từ Pancake sẽ bị block lại theo keyword trong mỗi lần nhận.
- Nếu cần theo dõi số lượng block theo thời gian, nên thêm metrics/log aggregation ở Phase 3 hoặc task riêng.
