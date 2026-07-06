# Task List Phase 5: Test và rollout

## Mục tiêu

Phase 5 hoàn thiện test coverage và rollout checklist cho tính năng tìm ảnh trong Google Drive folder con trong Pancake reply.

Kết quả mong muốn:

- Unit test cover Google Drive children query và traversal giới hạn.
- Pancake webhook test cover ảnh nested và fallback không có ảnh.
- Regression test đảm bảo Drive file link trực tiếp và folder có ảnh trực tiếp không bị ảnh hưởng.
- Rollout có log đủ để theo dõi trong production.

## Đầu vào đã chốt

- Các phase 1-4 đã implement.
- Test không gọi Google Drive hoặc Pancake thật.
- Max depth là 3 tầng.
- Chỉ dùng page đầu.
- Chỉ random 1 folder con mỗi tầng.

## Ngoài phạm vi Phase 5

- Không load test webhook production.
- Không tạo dashboard monitoring mới.
- Không migrate dữ liệu cache bắt buộc.
- Không tạo dữ liệu Google Drive thật trong test suite.

## File chính dự kiến sửa

- [tests/test_google_drive_image_service.py](../../tests/test_google_drive_image_service.py)
- [tests/test_pancake_drive_image_service.py](../../tests/test_pancake_drive_image_service.py)
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)
- `tests/test_google_drive_folder_traversal_service.py`, nếu tách helper riêng.

## Checklist

### 1. Unit test Google Drive service

- [x] Test query children gồm JPG, PNG và folder MIME type.
- [x] Test root folder có ảnh trực tiếp chỉ gọi 1 request.
- [x] Test ảnh nằm ở child folder depth 2 gọi 2 request.
- [x] Test ảnh nằm ở grandchild folder depth 3 gọi 3 request.
- [x] Test không gọi depth 4.
- [x] Test nhiều child folders chỉ chọn 1 folder con.
- [x] Test nhánh random không có ảnh thì không thử sibling khác.
- [x] Test `nextPageToken` không tạo request page 2.
- [x] Test folder không có ảnh và không có child folder trả `drive_folder_no_images`.
- [x] Test tầng 3 không có ảnh nhưng còn child folder trả `drive_folder_no_images_within_depth_limit`.

### 2. Unit test Pancake prepare reply

- [x] Test Pancake chọn ảnh từ root folder có ảnh trực tiếp.
- [x] Test Pancake chọn ảnh từ folder con.
- [x] Test Pancake chọn ảnh từ grandchild folder.
- [x] Test nested image được chuyển thành Drive file view URL.
- [x] Test `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` vẫn giới hạn ảnh.
- [x] Test color filter vẫn dùng `drive_file_name` từ ảnh nested.
- [x] Test traversal error được ghi vào `pancake_drive_reply.errors`.
- [x] Test không gọi cache/download/upload khi không có `drive_file_urls`.

### 3. Regression test flow hiện tại

- [x] Test Drive file link trực tiếp không đổi.
- [x] Test Drive folder có ảnh trực tiếp không đổi.
- [x] Test AI reply không Drive link không gọi Drive lookup.
- [x] Test text-only reply không regression.
- [x] Test dangerous keyword block vẫn chạy trước Drive image reply nếu liên quan.
- [x] Test bot pause/admin takeover vẫn suppress reply như hiện tại.

### 4. Rollout

- [x] Chạy `pytest -q`.
- [x] Kiểm tra log không lộ Google Drive API key.
- [x] Kiểm tra log không lộ Pancake access token.
- [x] Kiểm tra config `GOOGLE_DRIVE_FOLDER_LOOKUP_MAX_DEPTH` nếu có.
- [ ] Theo dõi count `drive_folder_no_images` sau deploy.
- [ ] Theo dõi count `drive_folder_no_images_within_depth_limit` sau deploy.
- [ ] Theo dõi latency Google Drive lookup sau deploy.

## Acceptance criteria

- [x] Toàn bộ test mới pass.
- [x] Regression test hiện tại pass.
- [x] Không có external service dependency trong test.
- [x] Max 3 request/root folder được chứng minh bằng test.
- [x] Page đầu là page duy nhất được chứng minh bằng test.
- [x] Có checklist rollout rõ ràng.

## Ghi chú mở

- Nên chuẩn bị một Drive folder test nội bộ có cấu trúc 3 tầng để QA thủ công sau deploy.
- Nếu production có nhiều folder con rỗng xen kẽ folder có ảnh, random 1 nhánh có thể miss ảnh; khi đó cần phase sau để scan nhiều nhánh có giới hạn.
- Nếu Drive folder thường có hơn 1000 child items, cần xem lại quyết định chỉ dùng page đầu.
