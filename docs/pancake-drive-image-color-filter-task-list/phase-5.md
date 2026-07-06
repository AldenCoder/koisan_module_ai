# Task List Phase 5: Test và rollout

## Mục tiêu

Phase 5 hoàn thiện test coverage và rollout checklist cho tính năng chọn ảnh theo màu từ Google Drive filename trong Pancake reply.

Kết quả mong muốn:

- Unit test cover parser filename, detect màu từ text, cache metadata, và selection theo màu.
- Regression test đảm bảo reply không có Drive link không bị ảnh hưởng.
- Rollout có log đủ để theo dõi trong production.

## Đầu vào đã chốt

- Các phase 1-4 đã implement.
- Config color map đã có default tối thiểu.
- Test không gọi external Google Drive hoặc Pancake thật.

## Ngoài phạm vi Phase 5

- Không load test webhook production.
- Không tạo dashboard monitoring mới.
- Không migrate dữ liệu cache bắt buộc.

## File chính dự kiến sửa

- [tests/test_google_drive_image_service.py](../../tests/test_google_drive_image_service.py)
- [tests/test_pancake_drive_image_service.py](../../tests/test_pancake_drive_image_service.py)
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)
- `tests/test_pancake_drive_image_color_service.py`, nếu tách helper riêng.

## Checklist

### 1. Unit test parser và color map

- [x] Test filename `vay_da_hoi_do.jpg -> do`.
- [x] Test filename `vay_da_hoi_xanhngoc.jpg -> xanhngoc`.
- [x] Test filename `vay_do_da_hoi.jpg -> None`.
- [x] Test filename `vay_da_hoi_xanh_ngoc.jpg -> None` trong phase đầu.
- [x] Test text `màu đỏ -> do`.
- [x] Test text `màu xanh ngọc -> xanhngoc`.
- [x] Test text không dấu `mau do -> do`.
- [x] Test text `váy đỏ -> None` vì thiếu trigger `màu`.
- [x] Test text `mẫu đỏ -> None` để tránh nhầm với `màu đỏ`.
- [x] Test text không có cụm `màu + tên màu` -> `None`.

### 2. Unit test cache metadata

- [x] Test cache ghi `drive_file_name`.
- [x] Test cache ghi `drive_file_color`.
- [x] Test cache cũ thiếu metadata vẫn đọc được.
- [x] Test cache cũ thiếu metadata vẫn reuse được khi không có `requested_color`.
- [x] Test cache cũ thiếu `drive_file_name` bị xóa khi có `requested_color`.
- [x] Test cache cũ thiếu `drive_file_color` bị xóa khi có `requested_color`.
- [x] Test sau khi xóa entry thiếu metadata, service chạy lại download/cache và ghi metadata mới.
- [x] Test không reuse `content_id` cũ của entry thiếu metadata trong flow có `requested_color`.
- [x] Test record `content_id` preserve metadata.
- [x] Test remove local preserve metadata.

### 3. Unit test webhook selection

- [x] Test AI reply không Drive link thì không gọi color filter.
- [x] Test AI reply Drive link không màu thì giữ random selection.
- [x] Test AI reply Drive link có cụm `màu + tên màu` thì chỉ chọn ảnh match.
- [x] Test AI reply Drive link có tên màu đứng lẻ nhưng không có chữ `màu` thì giữ random selection.
- [x] Test không match màu thì fallback random theo logic cũ.
- [x] Test nhiều ảnh match thì giới hạn max count.
- [x] Test nhiều folder link thì áp dụng cùng requested color cho từng folder.

### 4. Rollout

- [x] Chạy `pytest -q`.
- [x] Bật log color filter ở mức đủ debug.
- [ ] Kiểm tra config color map production.
- [ ] Kiểm tra naming convention folder ảnh mẫu.
- [ ] Theo dõi reason `drive_color_no_match_random_fallback` sau deploy.

## Acceptance criteria

- [x] Toàn bộ test mới pass.
- [x] Regression test hiện tại pass.
- [x] Không có external service dependency trong test.
- [x] Có checklist rollout rõ ràng.

## Ghi chú mở

- Nên chuẩn bị một folder Drive test nội bộ có đủ màu `do`, `den`, `xanhngoc` để QA thủ công sau deploy.
