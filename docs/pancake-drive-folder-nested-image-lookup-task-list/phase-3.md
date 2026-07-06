# Task List Phase 3: Tích hợp Pancake prepare reply

## Mục tiêu

Phase 3 tích hợp nested Drive folder lookup vào flow chuẩn bị Pancake reply. Sau khi `GoogleDriveImageService` trả ảnh từ root folder hoặc folder con, Pancake flow vẫn chọn ảnh, tạo Drive file view URL, cache/download/upload và gửi ảnh theo logic hiện tại.

Kết quả mong muốn:

- Pancake không cần biết ảnh đến từ root folder hay folder con.
- Ảnh tìm được ở folder con vẫn đi qua flow cache/download/upload hiện tại.
- Color filter vẫn dùng `drive_file_name` từ ảnh tìm được.
- Nếu traversal không tìm thấy ảnh, text vẫn gửi được và cache ảnh không chạy.

## Đầu vào đã chốt

- `GoogleDriveImageService.lookup_folder_images(...)` vẫn là entrypoint folder lookup.
- `DriveFolderImageResult.images` có danh sách ảnh nếu traversal tìm được ảnh.
- `DriveFolderImageResult.error` có reason mới nếu traversal dừng mà không có ảnh.
- Raw Drive folder link vẫn bị tách khỏi text reply như hiện tại.

## Ngoài phạm vi Phase 3

- Không đổi endpoint gửi Pancake message.
- Không đổi `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT`.
- Không đổi rule color detection từ AI text.
- Không đổi cache JSON format ngoài metadata optional đã có.
- Không fallback gửi raw Drive folder link.

## File chính dự kiến sửa

- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [app/services/pancake_drive_image_service.py](../../app/services/pancake_drive_image_service.py)
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)
- [tests/test_pancake_drive_image_service.py](../../tests/test_pancake_drive_image_service.py), nếu helper Pancake cần đổi.

## Checklist

### 1. Nhận ảnh từ nested lookup

- [x] Pancake vẫn gọi `GoogleDriveImageService().lookup_folder_images(prepared.drive_folder_urls)`.
- [x] Với folder result có `images`, chọn ảnh như hiện tại.
- [x] Ảnh từ folder con được chuyển thành `https://drive.google.com/file/d/{drive_file_id}/view`.
- [x] Dedupe `drive_file_id` với danh sách đã chọn trước đó.
- [x] Không phụ thuộc ảnh đến từ root folder hay folder con.

Kết quả mong muốn:
  Pancake prepare reply dùng nested image results giống direct folder image results.

### 2. Giữ giới hạn chọn ảnh

- [x] `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` vẫn áp dụng cho mỗi Drive folder link.
- [x] Nếu folder tìm được có ít ảnh hơn giới hạn, chọn số ảnh hiện có.
- [x] Nếu folder tìm được có nhiều ảnh hơn giới hạn, random tối đa giới hạn.
- [x] Nếu AI trả nhiều Drive folder link, xử lý từng folder link theo thứ tự hiện tại.

Kết quả mong muốn:
  Nested lookup không làm tăng số ảnh gửi vượt giới hạn business hiện tại.

### 3. Tương tác với color filter

- [x] Giữ `drive_file_name` từ `DriveImageResult`.
- [x] Detect `drive_file_color` từ filename như hiện tại.
- [x] Nếu có `requested_color`, filter ảnh nested theo `drive_file_color`.
- [x] Nếu không có ảnh match màu, fallback random theo logic color filter hiện tại.
- [x] Ghi `color_filter_reason` đúng khi fallback hoặc không match.

Kết quả mong muốn:
  Ảnh nằm trong folder con vẫn được chọn đúng màu nếu filename có metadata màu.

### 4. Xử lý error result

- [x] Nếu folder result có `error`, tăng `drive_folder_error_count`.
- [x] Thêm error vào `pancake_drive_reply.errors`.
- [x] Error gồm `drive_folder_url`, `drive_folder_id`, `reason`.
- [x] Không tạo `drive_file_urls` từ folder lỗi.
- [x] Không chạy `PancakeDriveImageService.ensure_local_images` nếu không có `drive_file_urls`.

Kết quả mong muốn:
  Lookup không có ảnh không tạo cache/download/upload rỗng hoặc sai.

### 5. Test phase 3

- [x] Test Pancake prepare reply chọn ảnh từ folder con.
- [x] Test Pancake prepare reply giữ metadata filename từ folder con.
- [x] Test color filter dùng ảnh nested đúng màu.
- [x] Test traversal error được đưa vào `pancake_drive_reply.errors`.
- [x] Test không gọi cache service khi không có `drive_file_urls`.

## Acceptance criteria

- [x] Pancake gửi được ảnh khi ảnh nằm trong folder con được chọn.
- [x] Pancake vẫn giới hạn số ảnh theo `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT`.
- [x] Pancake vẫn support color filter với ảnh nested.
- [x] Pancake vẫn gửi text nếu nested lookup lỗi hoặc không có ảnh.
- [x] Test phase này pass.

## Ghi chú mở

- Nếu caller hiện tại không cần expose traversal metadata ra response, có thể chỉ lưu/log metadata rút gọn.
- Nên giữ public contract của `prepare_pancake_drive_reply` ổn định để tránh regression với Drive file link trực tiếp.
