# Task List Phase 2: Lưu metadata tên/màu vào Pancake image cache

## Mục tiêu

Phase 2 mở rộng `storage/pancake_image_cache.json` để lưu thêm `drive_file_name` và `drive_file_color` cho từng `drive_file_id`. Metadata này phục vụ debug, reuse, và lựa chọn ảnh đúng màu trong các lần xử lý sau.

Kết quả mong muốn:

- Cache item có thể lưu `drive_file_name`.
- Cache item có thể lưu `drive_file_color`.
- Các update cache hiện tại không làm mất metadata tên/màu.
- Cache cũ không có metadata tên/màu vẫn đọc được trong flow không filter màu.
- Khi flow có `requested_color`, cache item thiếu `drive_file_name` hoặc `drive_file_color` bị xóa khỏi `items` và được chạy lại từ bước download/cache để tạo entry đủ metadata.

## Đầu vào đã chốt

- `drive_file_id` vẫn là key chính của cache.
- File local vẫn lưu theo `storage/pancake_images/{drive_file_id}.jpg`.
- Metadata tên/màu là optional.
- Metadata tên/màu là bắt buộc để reuse `content_id` trong flow có `requested_color`.

## Ngoài phạm vi Phase 2

- Không đổi endpoint upload Pancake.
- Không đổi format local file path.
- Không implement UI quản lý cache.
- Không migrate bắt buộc cache cũ.

## File chính dự kiến sửa

- [app/services/pancake_drive_image_service.py](../../app/services/pancake_drive_image_service.py)
- [tests/test_pancake_drive_image_service.py](../../tests/test_pancake_drive_image_service.py)

## Checklist

### 1. Ghi metadata vào cache

- [x] Thêm `drive_file_name` vào cache updates khi có metadata.
- [x] Thêm `drive_file_color` vào cache updates khi detect được màu.
- [x] Khi download ảnh, merge metadata vào entry hiện có.
- [x] Khi dùng file local có sẵn, vẫn cập nhật metadata nếu có.
- [x] Khi reuse `content_id`, result vẫn có thể trả metadata từ cache.

Kết quả mong muốn:
  Cache có đủ metadata để debug và hỗ trợ color filter.

### 2. Không mất metadata khi update cache

- [x] `record_uploaded_content_id` merge entry hiện có thay vì replace.
- [x] `remove_local_image_for_drive_file_id` không xóa tên/màu.
- [x] Update size/mime không xóa tên/màu.
- [x] Cache cũ thiếu field tên/màu vẫn không crash.

Kết quả mong muốn:
  Metadata tên/màu sống cùng cache item qua các lần download/upload/reuse.

### 3. Xử lý cache cũ thiếu metadata khi có requested color

- [x] Nếu flow không có `requested_color`, cache cũ thiếu tên/màu vẫn có thể reuse theo logic hiện tại.
- [x] Nếu flow có `requested_color` và cache item thiếu `drive_file_name`, xóa entry khỏi `items`.
- [x] Nếu flow có `requested_color` và cache item thiếu `drive_file_color`, xóa entry khỏi `items`.
- [x] Sau khi xóa entry thiếu metadata, chạy lại từ bước download/cache.
- [x] Entry mới sau khi chạy lại phải lưu `drive_file_id`, `drive_file_name`, `drive_file_color`, `direct_download_url`, `local_path`.
- [x] Không dùng `content_id` cũ của entry thiếu metadata để gửi ảnh theo màu.

Kết quả mong muốn:
  Cache cũ không làm BE gửi ảnh sai màu khi bắt đầu dùng color filter.

### 4. Test phase 2

- [x] Test cache sau download có `drive_file_name`.
- [x] Test cache sau download có `drive_file_color`.
- [x] Test record `content_id` không làm mất tên/màu.
- [x] Test remove local file không làm mất tên/màu.
- [x] Test cache cũ thiếu tên/màu vẫn đọc được.
- [x] Test cache cũ thiếu tên/màu bị xóa khi có `requested_color`.
- [x] Test sau khi xóa cache cũ, service chạy lại download/cache và ghi metadata mới.

## Acceptance criteria

- [x] Cache item lưu được `drive_file_name`.
- [x] Cache item lưu được `drive_file_color`.
- [x] Các update cache hiện tại preserve metadata tên/màu.
- [x] Cache item thiếu metadata không được reuse trong flow có `requested_color`.
- [x] Unit test phase này pass.

## Ghi chú mở

- Chỉ tăng cache version nếu cần migration bắt buộc. Nếu field optional thì có thể giữ `version: 1`.
