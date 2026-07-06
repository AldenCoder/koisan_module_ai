# Task List Phase 1: Lấy tên ảnh và detect màu từ Drive metadata

## Mục tiêu

Phase 1 bổ sung metadata ảnh từ Google Drive folder lookup. Sau khi BE lấy được danh sách ảnh trong folder, BE cần giữ `drive_file_name`, detect `drive_file_color` từ filename, và đưa metadata này vào object nội bộ để các phase sau cache/filter/gửi ảnh sử dụng.

Kết quả mong muốn:

- Google Drive folder lookup có field `name`.
- Mỗi ảnh hợp lệ có `drive_file_id`, `drive_file_name`, `drive_file_color` nếu parse được.
- File không parse được màu vẫn có thể tham gia random selection khi không có requested color.

## Đầu vào đã chốt

- Folder lookup chỉ lấy ảnh trực tiếp trong folder.
- Chỉ nhận `image/jpeg` và `image/png`.
- Filename đặt màu ở token cuối trước extension.
- Màu nhiều từ viết liền không dấu.

## Ngoài phạm vi Phase 1

- Không ghi cache JSON.
- Không upload ảnh lên Pancake.
- Không gửi message ảnh.
- Không detect màu từ AI text.

## File chính dự kiến sửa

- [app/services/google_drive_image_service.py](../../app/services/google_drive_image_service.py)
- [app/services/pancake_drive_image_service.py](../../app/services/pancake_drive_image_service.py)
- `app/services/pancake_drive_image_color_service.py`, nếu tách helper riêng.
- [tests/test_google_drive_image_service.py](../../tests/test_google_drive_image_service.py)
- `tests/test_pancake_drive_image_color_service.py`, nếu tách helper riêng.

## Checklist

### 1. Giữ tên ảnh từ Google Drive

- [x] Đảm bảo fields Google Drive có `files(id,name,mimeType,size)`.
- [x] Normalize `drive_file_name` thành string an toàn.
- [x] Giữ `drive_file_name` trong folder result.
- [x] Không log Google Drive API key.

Kết quả mong muốn:
  BE có tên ảnh thật từ Drive để parse màu và debug.

### 2. Detect màu từ filename

- [x] Bỏ extension cuối `.jpg`, `.jpeg`, `.png`.
- [x] Lowercase filename.
- [x] Split filename theo `_`.
- [x] Lấy token cuối làm candidate color.
- [x] Chỉ nhận candidate nếu nằm trong bảng màu.
- [x] Không ghi `drive_file_color` nếu token cuối không hợp lệ.

Kết quả mong muốn:
  `vay_da_hoi_do.jpg` parse thành `do`, `vay_da_hoi_xanhngoc.jpg` parse thành `xanhngoc`.

### 3. Test phase 1

- [x] Test parse `do` từ `vay_da_hoi_do.jpg`.
- [x] Test parse `xanhngoc` từ `vay_da_hoi_xanhngoc.jpg`.
- [x] Test không parse từ `vay_do_da_hoi.jpg`.
- [x] Test không parse từ filename thiếu màu.
- [x] Test folder lookup result giữ `name` và `drive_file_color`.

## Acceptance criteria

- [x] Folder lookup giữ được `drive_file_name`.
- [x] BE detect được `drive_file_color` theo filename convention.
- [x] File không có màu hợp lệ không làm hỏng folder lookup.
- [x] Unit test phase này pass.

## Ghi chú mở

- Với Drive file link trực tiếp, có thể bổ sung metadata bằng Google Drive `files.get` ở phase sau nếu cần.
