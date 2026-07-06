# Task List Phase 0: Chốt giải pháp chọn ảnh Pancake Drive theo màu

## Mục tiêu

Phase 0 chốt phạm vi và contract tổng thể cho flow chọn ảnh đúng màu từ Google Drive folder trong Pancake reply. Flow này chỉ chạy sau khi AI trả response có Drive link; nếu AI reply không có Drive link thì BE không detect màu và không đổi flow text reply hiện tại.

Phase này chỉ chốt giải pháp và ranh giới trách nhiệm. Chưa sửa code, chưa thay đổi cache, chưa đổi logic chọn ảnh.

## Quyết định cần chốt

- BE chỉ chạy color filter khi AI reply có Drive file link hoặc Drive folder link.
- Nếu AI reply không có Drive link, BE không detect màu và không đổi flow hiện tại.
- Nếu AI reply có Drive link nhưng không có cụm `màu + tên màu`, BE giữ random selection hiện tại.
- Nếu AI reply có Drive link và có cụm `màu + tên màu`, BE chọn ảnh theo `drive_file_color`.
- Nếu có cụm `màu + tên màu` nhưng không có ảnh match, BE fallback random theo logic cũ.
- BE không detect màu từ tên màu đứng lẻ như `đỏ`, `xanh ngọc` nếu không có chữ `màu` ngay trước.
- BE không được nhầm `mẫu đỏ` thành `màu đỏ`.
- Tên ảnh đặt màu ở token cuối trước extension, ví dụ `vay_da_hoi_do.jpg`.
- Màu nhiều từ viết liền không dấu, ví dụ `xanhngoc` cho `xanh ngọc`.

## Ngoài phạm vi Phase 0

- Chưa implement parser màu.
- Chưa thay đổi Google Drive folder lookup.
- Chưa ghi `drive_file_name` hoặc `drive_file_color` vào cache.
- Chưa thay đổi logic gửi ảnh Pancake.
- Chưa thêm test.

## File tài liệu liên quan

- [docs/pancake-drive-image-color-filter.md](../pancake-drive-image-color-filter.md)
- [docs/pancake-drive-link-image-reply.md](../pancake-drive-link-image-reply.md)
- [docs/pancake-drive-image-color-filter-task-list/phase-1.md](phase-1.md)
- [docs/pancake-drive-image-color-filter-task-list/phase-2.md](phase-2.md)
- [docs/pancake-drive-image-color-filter-task-list/phase-3.md](phase-3.md)
- [docs/pancake-drive-image-color-filter-task-list/phase-4.md](phase-4.md)
- [docs/pancake-drive-image-color-filter-task-list/phase-5.md](phase-5.md)

## Checklist

### 1. Chốt điều kiện kích hoạt

- [x] Xác nhận chỉ chạy color filter khi AI reply có Drive link.
- [x] Xác nhận reply không có Drive link không detect màu.
- [x] Xác nhận reply không có Drive link không gọi folder lookup/cache màu.
- [x] Xác nhận chỉ detect `requested_color` từ pattern `màu + tên màu`.
- [x] Xác nhận text có màu đứng lẻ nhưng không có chữ `màu` thì không filter.
- [x] Xác nhận `mẫu đỏ` không bị detect nhầm thành `màu đỏ`.
- [x] Xác nhận text-only reply không bị regression.

Kết quả mong muốn:
  Color filter chỉ là phần mở rộng của Drive image reply, không ảnh hưởng flow không có ảnh.

### 2. Chốt naming convention

- [x] Xác nhận màu nằm ở token cuối filename.
- [x] Xác nhận token được ngăn cách bằng `_`.
- [x] Xác nhận màu nhiều từ viết liền không dấu.
- [x] Xác nhận `vay_da_hoi_xanhngoc.jpg` tương ứng màu `xanh ngọc`.
- [x] Xác nhận không dùng token giữa filename để suy luận màu.

Kết quả mong muốn:
  BE có quy tắc deterministic để parse màu từ tên ảnh.

### 3. Chốt fallback

- [x] Xác nhận không có cụm `màu + tên màu` thì giữ random selection hiện tại.
- [x] Xác nhận có cụm `màu + tên màu` nhưng không match ảnh thì fallback random theo logic cũ.
- [x] Xác nhận vẫn gửi text nếu text hợp lệ.
- [x] Xác nhận reason `drive_color_no_match_random_fallback` cần được log khi fallback random.

Kết quả mong muốn:
  Khách vẫn nhận được ảnh khi folder chưa được đặt tên màu đúng convention.

## Acceptance criteria

- [x] Team chốt điều kiện kích hoạt color filter.
- [x] Team chốt rule `màu + tên màu` cho detect màu từ AI text.
- [x] Team chốt naming convention filename.
- [x] Team chốt fallback khi không có cụm `màu + tên màu` hoặc không match màu.
- [x] Team chốt không thay đổi flow không có Drive link.

## Ghi chú mở

- Nếu sau này cần một reply nhiều màu, nên mở rộng contract riêng thay vì nhồi vào phase đầu.
- Fallback random khi không match màu cần được log để sau deploy biết folder nào chưa đặt tên ảnh đúng convention.
