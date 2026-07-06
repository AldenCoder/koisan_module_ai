# Task List Phase 4: Fallback và xử lý lỗi an toàn

## Mục tiêu

Phase 4 bổ sung xử lý lỗi để luồng mới bền hơn trong production. Lỗi Drive hoặc lỗi media send không được làm mất phản hồi text của khách. Nếu gửi nhiều ảnh lỗi, BE fallback sang gửi từng ảnh.

Kết quả mong muốn:

- Text vẫn được gửi nếu có thể.
- Drive folder lỗi không làm crash toàn bộ flow.
- Bulk image send lỗi thì fallback single image send.
- Một ảnh lỗi thì skip ảnh đó và tiếp tục ảnh khác.

## Đầu vào đã chốt

- BE chỉ gửi 1-3 ảnh mỗi lượt.
- Bulk send dùng `message.attachments`.
- Single send dùng `message.attachment`.
- Image URL hợp lệ ưu tiên là `https://lh3.googleusercontent.com/d/{id}`.

## Ngoài phạm vi Phase 4

- Không thêm retry backoff nhiều lần ngoài fallback bulk sang single image.
- Không thêm queue/outbox persistent.
- Không download/rehost ảnh Drive.
- Không thêm dashboard metrics mới nếu chưa cần.

## File chính dự kiến sửa

- [app/services/facebook_message_service.py](../../app/services/facebook_message_service.py)
- [app/services/google_drive_image_service.py](../../app/services/google_drive_image_service.py)
- [app/api/v1/facebook_webhook.py](../../app/api/v1/facebook_webhook.py)
- [tests/test_facebook_message_service.py](../../tests/test_facebook_message_service.py)
- [tests/test_facebook_webhook_forward.py](../../tests/test_facebook_webhook_forward.py)

## Checklist

### 1. Xử lý lỗi Drive lookup

- [x] Folder URL invalid thì skip folder.
- [x] Google Drive API `403`/`404` thì log reason rút gọn.
- [x] Timeout/network error thì log và tiếp tục flow.
- [x] Một folder lỗi không làm mất ảnh từ folder khác.
- [x] Nếu không có ảnh nào, vẫn gửi text nếu có.

Kết quả mong muốn:
  Drive lỗi không làm khách mất phản hồi text.

### 2. Fallback Facebook image send

- [x] Bắt lỗi HTTP khi gửi `message.attachments`.
- [x] Bắt timeout/network exception.
- [x] Log `bulk_send_failed` với count ảnh và reason rút gọn.
- [x] Fallback gửi từng ảnh bằng `message.attachment`.
- [x] Một ảnh single-send lỗi thì skip và tiếp tục ảnh khác.

Kết quả mong muốn:
  Ảnh hợp lệ vẫn có cơ hội đến khách dù bulk send lỗi.

### 3. Validate và skip ảnh lỗi

- [x] Skip URL không phải `https`.
- [x] Skip host không nằm trong allowlist.
- [x] Skip URL trùng.
- [x] Không retry vô hạn với URL lỗi.
- [x] Không log full token hoặc secret trong URL/query.

Kết quả mong muốn:
  BE gửi media an toàn hơn và dễ debug hơn.

### 4. Observability

- [x] Log số Drive link tìm thấy.
- [x] Log số folder lookup thành công/thất bại.
- [x] Log số ảnh lấy được và số ảnh chọn gửi.
- [x] Log kết quả gửi text.
- [x] Log kết quả gửi ảnh bulk/fallback.
- [x] Không log `GOOGLE_DRIVE_API_KEY`, Facebook token, Bearer token Brain.

Kết quả mong muốn:
  Khi production lỗi, log đủ để biết lỗi nằm ở Brain data, Drive lookup, hay Facebook media send.

### 5. Test fallback

- [x] Test Drive folder invalid vẫn gửi text.
- [x] Test Drive API fail vẫn gửi text.
- [x] Test bulk send success thì không fallback.
- [x] Test bulk send fail thì fallback single send.
- [x] Test một single image fail thì tiếp tục ảnh khác.
- [x] Test tất cả ảnh fail không crash flow.
- [x] Test log/summary count đúng.

Kết quả mong muốn:
  Behavior lỗi chính được verify bằng test tự động.

## Acceptance criteria

- [x] Lỗi Drive không làm fail text response.
- [x] Bulk send lỗi có fallback single send.
- [x] Một ảnh lỗi không làm fail toàn bộ flow.
- [x] Log đủ count/reason để debug.
- [x] Không log secret.

## Ghi chú mở

- Nếu latency gửi từng ảnh cao, có thể tách queue/background worker ở phase sau.
- Nếu Facebook fetch ảnh Drive không ổn định, có thể nghiên cứu upload/rehost ảnh ở phase sau.
