# Task List Phase 4: Lưu message, fallback và logging

## Mục tiêu

Phase 4 đảm bảo flow chọn ảnh theo màu có metadata đủ để debug, fallback không làm mất text reply, và không log dữ liệu nhạy cảm.

Kết quả mong muốn:

- Bot message meta có thông tin màu và ảnh đã chọn ở mức rút gọn.
- Fallback random theo logic cũ khi không match màu.
- Text vẫn được gửi nếu media lỗi hoặc không match màu.
- Log đủ reason để debug nhưng không log token.

## Đầu vào đã chốt

- Flow gửi text trước, ảnh sau giữ nguyên.
- Object nội bộ có `requested_color`, `selected_drive_file_ids`, `drive_file_name`, `drive_file_color`.
- Cache có metadata tên/màu khi lookup được.

## Ngoài phạm vi Phase 4

- Không thêm UI xem log.
- Không thêm queue/outbox persistent.
- Không thay đổi schema database bắt buộc.

## File chính dự kiến sửa

- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [app/services/pancake_drive_image_service.py](../../app/services/pancake_drive_image_service.py)
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)

## Checklist

### 1. Lưu meta bot message

- [x] Lưu `requested_color`.
- [x] Lưu `color_filter_applied`.
- [x] Lưu `color_filter_reason`.
- [x] Lưu `selected_drive_file_ids`.
- [x] Lưu map rút gọn `drive_file_id -> drive_file_name`.
- [x] Lưu map rút gọn `drive_file_id -> drive_file_color`.
- [x] Lưu `content_ids` gửi thành công.

Kết quả mong muốn:
  Có đủ dữ liệu để kiểm tra vì sao BE chọn hoặc không chọn ảnh.

### 2. Fallback an toàn

- [x] Folder lookup lỗi vẫn gửi text nếu text hợp lệ.
- [x] Có màu nhưng không match thì fallback random theo logic cũ.
- [x] Download/upload lỗi vẫn gửi các ảnh còn lại nếu hợp lệ.
- [x] Tất cả ảnh lỗi thì không gửi image message.
- [x] Không gửi `content_ids` rỗng.

Kết quả mong muốn:
  Media lỗi không làm mất text reply và không gửi nhầm ảnh.

### 3. Logging

- [x] Log `drive_folder_id`.
- [x] Log `drive_file_id`.
- [x] Log `drive_file_name`.
- [x] Log `drive_file_color`.
- [x] Log `requested_color`.
- [x] Log số ảnh match màu.
- [x] Log reason `drive_color_no_match_random_fallback`.
- [x] Không log Google Drive API key.
- [x] Không log Pancake page token.

## Acceptance criteria

- [x] Bot message meta có thông tin color filter rút gọn.
- [x] Fallback giữ text reply khi media lỗi.
- [x] Fallback random theo logic cũ khi không match màu.
- [x] Log đủ để debug và không lộ token.
- [x] Unit test phase này pass.

## Ghi chú mở

- Nếu sau này có queue/background worker, metadata color filter nên đi cùng job payload để debug end-to-end.
