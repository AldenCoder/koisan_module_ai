# Task List Phase 3: Tích hợp webhook flow và xử lý lỗi gửi Pancake

## Mục tiêu

Phase 3 đảm bảo flow Pancake webhook truyền đúng `page_id` vào mọi call gửi reply/upload/media và lưu/log lỗi thiếu token theo page một cách rõ ràng. Khi thiếu token, backend không được gửi bằng token khác nhưng vẫn không làm mất user message đã nhận.

Kết quả mong muốn:

- Webhook vẫn lưu user message như hiện tại.
- Reply text dùng `page_id` đã normalize.
- Upload ảnh dùng `page_id` đã normalize.
- Gửi `content_ids` dùng `page_id` đã normalize.
- Missing token theo page được phản ánh trong `reply_result` hoặc `pancake_drive_image_send_result`.
- Không có API call Pancake nếu thiếu token.

## Đầu vào đã chốt

- `normalize_pancake_payload` trả `page_id`.
- `normalized["page_id"]` là source of truth khi gửi Pancake API.
- Phase 2 đã sửa service gửi Pancake để lookup token theo page.
- Missing token là lỗi cấu hình non-retryable.
- Không fallback token mặc định.

## Ngoài phạm vi Phase 3

- Không đổi AI prompt/response.
- Không đổi duplicate/admin pause.
- Không đổi cách lưu `Conversation`/`Message` trừ meta lỗi nếu cần.
- Không đổi Drive image cache/content_id reuse.
- Không thêm queue retry persistent.

## File chính dự kiến sửa

- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)
- [app/services/pancake_webhook_normalize_service.py](../../app/services/pancake_webhook_normalize_service.py), nếu cần guard `page_id`.

## Checklist

### 1. Kiểm tra `page_id` trong normalize

- [x] Xác nhận normalize lấy `page_id` từ root payload.
- [x] Xác nhận normalize fallback từ `data.message.page_id` nếu root thiếu.
- [x] Nếu không có `page_id`, result normalize phải có reason rõ.
- [x] Không gửi Pancake API khi `page_id` rỗng.
- [x] Test payload thiếu `page_id` không đi vào send flow.

Kết quả mong muốn:
  Mọi send flow có `page_id` tin cậy để lookup token.

### 2. Text reply path

- [x] `send_pancake_reply` nhận `page_id=str(normalized.get("page_id") or "")`.
- [x] Nếu service trả missing token, webhook return/send result giữ reason đó.
- [x] Bot message meta lưu `reply_result` có reason.
- [x] Không gọi image send nếu text reply fail vì missing token.
- [x] Log có `page_id`, `conversation_id`, `message_mid`, reason.
- [x] Log không có token.

Kết quả mong muốn:
  Text reply không thể gửi nhầm page khi thiếu token.

### 3. Upload ảnh path

- [x] `_send_pancake_drive_images` dùng `page_id` từ `normalized`.
- [x] `upload_pancake_content` nhận đúng `page_id`.
- [x] Missing token khi upload được ghi vào `upload_results`.
- [x] Missing token khi upload được ghi vào `upload_errors`.
- [x] Nếu tất cả ảnh lỗi vì missing token, text success vẫn được giữ nếu text đã gửi thành công.
- [x] Không retry upload khi missing token.

Kết quả mong muốn:
  Media upload dùng đúng token theo page và lỗi cấu hình không phá text đã gửi.

### 4. Send `content_ids` path

- [x] `send_pancake_content_ids` nhận đúng `page_id`.
- [x] Nếu reuse `content_id` không cần upload, vẫn lookup token đúng page khi gửi message ảnh.
- [x] Missing token khi gửi `content_ids` trả reason rõ.
- [x] `pancake_drive_image_send_result` lưu reason.
- [x] Không log token.

Kết quả mong muốn:
  Reuse `content_id` vẫn không bỏ qua rule token theo page.

### 5. Test phase 3

- [x] Test webhook page A gửi text bằng token A.
- [x] Test webhook page B gửi text bằng token B.
- [x] Test page thiếu token không gọi Pancake reply.
- [x] Test page thiếu token vẫn lưu user message.
- [x] Test page thiếu token lưu bot/meta lỗi nếu flow có lưu.
- [x] Test upload image page A dùng token A.
- [x] Test reused `content_id` page B gửi bằng token B.
- [x] Test không fallback sang token cũ trong webhook flow.

Kết quả mong muốn:
  Webhook end-to-end bằng mock chứng minh mỗi page dùng đúng token.

## Acceptance criteria

- [x] Webhook truyền đúng `page_id` vào mọi Pancake service call.
- [x] Page chưa cấu hình token không gửi reply bằng token khác.
- [x] Missing token được lưu/log bằng reason rõ.
- [x] User message không mất khi send lỗi do thiếu token.
- [x] Test phase này pass.

## Ghi chú mở

- Nếu muốn alert vận hành, có thể gom reason `missing_pancake_page_access_token_for_page` trong logging/monitoring.
- Nếu có nhiều worker, env mapping phải đồng bộ ở mọi instance.
