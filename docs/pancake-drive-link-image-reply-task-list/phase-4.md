# Task List Phase 4: Lưu message, fallback và logging

## Mục tiêu

Phase 4 hoàn thiện behavior khi lưu bot response, xử lý lỗi từng bước và log đủ dữ liệu để debug. Flow phải đảm bảo lỗi ảnh không làm mất text reply, không log token, và không phá các guard hiện có như duplicate, bot pause, admin takeover.

Kết quả mong muốn:

- Bot text message lưu text đã tách raw Drive link.
- Metadata ảnh được lưu ở nơi đã chốt.
- Download/upload lỗi từng ảnh không làm crash toàn bộ reply.
- Nếu ảnh lỗi hết, text vẫn được gửi nếu hợp lệ.
- Log đủ reason để debug nhưng không lộ token.

## Đầu vào đã chốt

- User message vẫn lưu như flow Pancake hiện tại.
- Bot text message lưu `content` là text đã gửi hoặc chuẩn bị gửi.
- Image metadata có thể lưu trong `meta` của bot text message ở phase đầu.
- Không lưu file binary vào database.
- Không lưu token hoặc direct auth data vào `Message.meta`.

## Ngoài phạm vi Phase 4

- Không thêm bảng mới nếu chưa có yêu cầu riêng.
- Không build UI xem cache/image.
- Không thêm queue/outbox persistent nếu chưa có yêu cầu riêng.
- Không thay đổi schema database nếu meta hiện tại đủ dùng.

## File chính dự kiến sửa

- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [app/services/pancake_message_service.py](../../app/services/pancake_message_service.py)
- `app/services/pancake_drive_image_service.py`
- `tests/test_pancake_webhook.py`
- `tests/test_pancake_drive_image_service.py`

## Checklist

### 1. Lưu bot text message

- [x] Lưu bot text message như flow Pancake hiện tại.
- [x] `content` là text đã tách raw Drive link.
- [x] `meta.source` giữ source Pancake phù hợp.
- [x] `meta.reply_to_message_mid` trỏ về user message nếu flow hiện tại có dùng.
- [x] Không lưu raw Drive link trong `content` nếu link chỉ dùng để lấy ảnh.
- [x] Không lưu token hoặc auth data trong meta.

Kết quả mong muốn:
  Lịch sử hội thoại nội bộ hiển thị text sạch giống nội dung gửi khách.

### 2. Lưu metadata ảnh

- [x] Lưu `drive_file_ids` vào meta theo hướng đã chốt.
- [x] Lưu `drive_file_urls` vào meta nếu cần debug.
- [x] Lưu `content_ids` upload thành công.
- [x] Lưu response Pancake rút gọn cho text send.
- [x] Lưu response Pancake rút gọn cho image send.
- [x] Không lưu file binary vào database.
- [x] Nếu chọn lưu image bot message riêng, đảm bảo không làm lệch UI/history hiện tại.

Kết quả mong muốn:
  Có đủ dữ liệu điều tra ảnh nào đã được xử lý và gửi qua Pancake.

### 3. Fallback khi lỗi Drive/cache/download

- [x] Extract `drive_file_id` lỗi thì bỏ qua link đó.
- [x] Cache đọc lỗi có reason rõ ràng.
- [x] Download lỗi một ảnh thì tiếp tục ảnh khác.
- [x] Content type không hợp lệ thì bỏ qua ảnh đó.
- [x] Tất cả ảnh download lỗi thì vẫn gửi text nếu text hợp lệ.
- [x] Không gửi image message nếu không có file local/content id hợp lệ.

Kết quả mong muốn:
  Lỗi ảnh không làm mất text reply và không làm request crash.

### 4. Fallback khi lỗi Pancake upload/send

- [x] Upload lỗi một ảnh thì tiếp tục ảnh khác.
- [x] Upload thiếu `content_id` thì bỏ qua ảnh đó.
- [x] Nếu upload được một phần, gửi các `content_ids` thành công.
- [x] Nếu gửi text thất bại, log reason rõ ràng.
- [x] Nếu gửi image message thất bại sau khi text đã gửi, log reason rõ ràng.
- [x] Không retry vô hạn.
- [x] Không gửi lại text nhiều lần do lỗi ảnh.

Kết quả mong muốn:
  Flow có partial success rõ ràng và không tạo spam/loop.

### 5. Logging an toàn

- [x] Log `drive_file_id`.
- [x] Log `page_id`.
- [x] Log `conversation_id` hoặc `pancake_conversation_id`.
- [x] Log `content_id` khi có.
- [x] Log reason lỗi theo từng bước.
- [x] Không log token.
- [x] Không log auth header.
- [x] Không log URL đầy đủ nếu URL chứa token/query nhạy cảm.

Kết quả mong muốn:
  Production có đủ dữ liệu debug mà không lộ thông tin nhạy cảm.

### 6. Test phase 4

- [x] Test bot message lưu text đã tách Drive link.
- [x] Test meta lưu `drive_file_ids` và `content_ids`.
- [x] Test download lỗi một ảnh thì ảnh khác vẫn được xử lý.
- [x] Test upload lỗi một ảnh thì content id khác vẫn được gửi.
- [x] Test tất cả ảnh lỗi thì vẫn gửi text nếu text hợp lệ.
- [x] Test không gửi image message khi `content_ids` rỗng.
- [x] Test token không xuất hiện trong log.
- [x] Test duplicate/pause/admin takeover behavior không đổi.

Kết quả mong muốn:
  Error path chính được cover bằng mock và không cần external service.

## Acceptance criteria

- [x] Bot text message lưu nội dung sạch.
- [x] Image metadata được lưu theo hướng đã chốt.
- [x] Lỗi ảnh không làm mất text reply.
- [x] Partial success gửi được ảnh thành công.
- [x] Log đủ reason và không lộ token.
- [x] Test phase này pass.

## Ghi chú mở

- Nếu sau này cần retry ảnh sau khi text đã gửi, nên đưa vào queue/outbox riêng để tránh gửi trùng text.
- Nếu UI cần hiển thị image message riêng, có thể tách bot message image ở phase sau.
