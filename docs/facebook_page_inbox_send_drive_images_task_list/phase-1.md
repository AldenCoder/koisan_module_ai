# Task List Phase 1: Chuẩn hóa Drive link và Google Drive image lookup

## Mục tiêu

Phase 1 tập trung vào phần BE tự xử lý Google Drive: tách Drive folder link từ data Brain trả về, lấy `folder_id`, gọi Google Drive API, lọc ảnh hợp lệ, và chuyển file id thành URL ảnh gửi được qua Messenger.

Kết quả mong muốn:

- BE có helper/service parse Drive folder link.
- BE có service lấy ảnh từ Google Drive folder.
- BE tạo được image URL dạng `https://lh3.googleusercontent.com/d/{id}`.
- BE trả kết quả nội bộ đủ để phase sau chọn 1-3 ảnh.

## Đầu vào đã chốt

- Drive link có thể đến từ `drive_folder_urls` hoặc nằm trong text Brain trả về.
- Google Drive API key nằm trong env `GOOGLE_DRIVE_API_KEY`.
- Chỉ lấy ảnh `image/jpeg` và `image/png`.
- Bỏ qua file đã xóa bằng điều kiện `trashed=false`.
- Field tối thiểu cần lấy: `id`, `name`, `mimeType`, `size`.

## Ngoài phạm vi Phase 1

- Không xử lý trực tiếp việc gửi Messenger message trong service Drive.
- Không implement logic catalog/intent bên trong Brain.
- Endpoint `/drive-images` cũ đã được remove ở phase implementation vì out-of-date với luồng mới.

## File chính dự kiến sửa

- [app/services/google_drive_image_service.py](../../app/services/google_drive_image_service.py)
- [app/core/config.py](../../app/core/config.py)
- [.env.example](../../.env.example)
- [tests/test_google_drive_image_service.py](../../tests/test_google_drive_image_service.py)

## Checklist

### 1. Parse Drive folder link

- [x] Parse link từ structured list `drive_folder_urls`.
- [x] Parse link từ plain text Brain trả về.
- [x] Hỗ trợ URL dạng `https://drive.google.com/drive/folders/{folder_id}`.
- [x] Hỗ trợ URL có query string.
- [x] Hỗ trợ URL có slash cuối.
- [x] Bỏ qua URL không phải Drive folder.
- [x] Loại duplicate folder URL trong cùng response.

Kết quả mong muốn:
  BE lấy được danh sách Drive folder URL sạch từ data Brain.

### 2. Tách folder id

- [x] Tách `folder_id` từ từng Drive folder URL.
- [x] Validate folder id rỗng hoặc sai format.
- [x] Trả lỗi theo từng folder thay vì crash toàn bộ batch.
- [x] Log folder-level error rút gọn.

Kết quả mong muốn:
  Folder lỗi không làm mất kết quả của folder khác.

### 3. Gọi Google Drive API

- [x] Dùng endpoint `GET https://www.googleapis.com/drive/v3/files`.
- [x] Build query `'FOLDER_ID' in parents and trashed=false`.
- [x] Lọc `mimeType='image/jpeg'` hoặc `mimeType='image/png'`.
- [x] Request fields `files(id,name,mimeType,size)`.
- [x] Truyền API key từ env, không hard-code.
- [x] Có timeout ngắn hợp lý.
- [x] Xử lý pagination nếu folder có nhiều ảnh.

Kết quả mong muốn:
  BE lấy được metadata ảnh từ Drive folder public.

### 4. Convert file id thành image URL

- [x] Bỏ qua file thiếu `id`.
- [x] Tạo `imageUrl` bằng `https://lh3.googleusercontent.com/d/{id}`.
- [x] Giữ metadata `name`, `mimeType`, `size` cho debug/log/test.
- [x] Chỉ trả ảnh có MIME type hợp lệ.

Kết quả mong muốn:
  Output của service có danh sách ảnh sẵn sàng cho phase chọn 1-3 ảnh.

### 5. Test service

- [x] Test parse Drive link từ structured payload.
- [x] Test parse Drive link từ plain text.
- [x] Test parse folder id thành công.
- [x] Test URL invalid không crash.
- [x] Test build query Google Drive.
- [x] Test parse response Google Drive.
- [x] Test convert file id thành `lh3.googleusercontent.com/d/{id}`.
- [x] Test nhiều folder trong một response Brain.

Kết quả mong muốn:
  Drive lookup được cover bằng unit test, không cần gọi Google/Facebook thật.

## Acceptance criteria

- [x] BE parse được Drive folder link từ data Brain.
- [x] BE tách được `folder_id`.
- [x] BE gọi Google Drive API bằng env key.
- [x] BE lọc được ảnh JPG/PNG.
- [x] BE tạo được image URL dạng `https://lh3.googleusercontent.com/d/{id}`.
- [x] Test phase này pass.

## Ghi chú mở

- Service Drive lookup hiện được gọi trực tiếp từ pipeline Facebook webhook; endpoint `/drive-images` cũ đã được remove.
- Nếu Drive folder chứa quá nhiều ảnh, phase này nên giới hạn metadata fetch hoặc pagination hợp lý để tránh latency cao.
