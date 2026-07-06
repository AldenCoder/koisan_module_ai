# Task List Phase 4: Lưu message, fallback và logging

## Mục tiêu

Phase 4 hoàn thiện phần metadata, fallback và logging cho nested Drive folder lookup trong Pancake flow. Mục tiêu là khi không gửi được ảnh, BE vẫn gửi text nếu hợp lệ và có đủ log/meta để debug nhánh folder đã đi qua.

Kết quả mong muốn:

- Bot message meta có thông tin nested lookup rút gọn.
- Log thể hiện folder id, depth, nhánh random và reason lỗi.
- Không log token, API key hoặc binary image content.
- Text reply không bị mất khi media lookup lỗi.

## Đầu vào đã chốt

- Traversal metadata có thể gồm `lookup_depth`, `visited_folder_ids`, `selected_child_folder_ids`, `page_truncated`.
- Folder-level error gồm `drive_folder_no_images` và `drive_folder_no_images_within_depth_limit`.
- Pancake flow gửi text trước, gửi ảnh sau.

## Ngoài phạm vi Phase 4

- Không đổi thuật toán traversal.
- Không đổi cache/download/upload ảnh.
- Không đổi Pancake API payload.
- Không thêm dashboard monitoring mới.
- Không lưu file binary vào database.

## File chính dự kiến sửa

- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [app/services/google_drive_image_service.py](../../app/services/google_drive_image_service.py)
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)
- [tests/test_google_drive_image_service.py](../../tests/test_google_drive_image_service.py)

## Checklist

### 1. Lưu metadata vào Pancake reply object

- [x] `pancake_drive_reply.drive_folder_results` có traversal metadata rút gọn.
- [x] `pancake_drive_reply.drive_folder_error_count` tăng khi folder result có error.
- [x] `pancake_drive_reply.errors` có reason folder-level.
- [x] `selected_drive_file_ids` chỉ gồm ảnh thật sự được chọn.
- [x] Không đưa dữ liệu quá lớn hoặc binary vào response/meta.

Kết quả mong muốn:
  Debug response đủ biết vì sao folder không có ảnh hoặc ảnh được chọn từ đâu.

### 2. Lưu metadata vào bot message meta

- [x] Bot message meta có `pancake_drive_reply`.
- [x] Bot message meta có `pancake_drive_image_cache_result` nếu cache chạy.
- [x] Bot message meta có `pancake_drive_image_send_result` nếu gửi ảnh chạy.
- [x] Meta không lưu Google Drive API key.
- [x] Meta không lưu Pancake access token.

Kết quả mong muốn:
  Có thể kiểm tra lại một conversation để biết nested lookup đã xử lý thế nào.

### 3. Logging

- [x] Log `drive_folder_id`.
- [x] Log `lookup_depth`.
- [x] Log `visited_folder_ids`.
- [x] Log `selected_child_folder_ids`.
- [x] Log `image_count`.
- [x] Log `child_folder_count`.
- [x] Log `page_truncated`.
- [x] Log reason `drive_folder_no_images`.
- [x] Log reason `drive_folder_no_images_within_depth_limit`.
- [x] Không log full Google Drive request URL có `key`.

Kết quả mong muốn:
  Production log đủ để debug miss ảnh mà không lộ secret.

### 4. Fallback text reply

- [x] Nếu nested lookup lỗi nhưng text hợp lệ, vẫn gửi text.
- [x] Nếu text gửi thành công nhưng không có ảnh, response vẫn `ok` theo text send result.
- [x] Nếu cache/download/upload lỗi hết, không gửi image message.
- [x] Nếu gửi image message lỗi, log response rút gọn.
- [x] Không retry traversal qua sibling folder trong fallback.

Kết quả mong muốn:
  Khách vẫn nhận được câu trả lời text khi media lỗi hoặc không tìm thấy ảnh.

### 5. Test phase 4

- [x] Test bot meta có `drive_folder_results`.
- [x] Test bot meta có `drive_folder_error_count`.
- [x] Test text vẫn gửi khi nested lookup trả `drive_folder_no_images`.
- [x] Test text vẫn gửi khi nested lookup trả `drive_folder_no_images_within_depth_limit`.
- [x] Test không gửi `content_ids` rỗng.

## Acceptance criteria

- [x] Metadata lookup được lưu rút gọn.
- [x] Logging không lộ secret.
- [x] Text reply không bị ảnh hưởng bởi lỗi media.
- [x] Không có image message khi không có `content_ids`.
- [x] Test phase này pass.

## Ghi chú mở

- Nếu `drive_folder_results` quá lớn, chỉ nên giữ ảnh đã chọn và error summary trong message meta.
- Nếu cần quan sát production tốt hơn, nên thêm counter theo reason ở hạ tầng log/monitoring thay vì mở rộng response cho khách.
