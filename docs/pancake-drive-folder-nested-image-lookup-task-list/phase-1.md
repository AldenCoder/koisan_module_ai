# Task List Phase 1: List ảnh và folder con từ Google Drive

## Mục tiêu

Phase 1 cập nhật Google Drive lookup để list được cả ảnh và folder con trong current folder. Phase này chưa implement traversal nhiều tầng; mục tiêu là có một fetch helper ổn định cho page đầu của một folder.

Kết quả mong muốn:

- BE gọi Google Drive API một lần cho current folder.
- Response gồm ảnh `image/jpeg`, ảnh `image/png` và folder con `application/vnd.google-apps.folder`.
- BE chỉ dùng page đầu tiên, không follow `nextPageToken`.
- Lỗi Google Drive vẫn được trả theo folder-level error như hiện tại.

## Đầu vào đã chốt

- Chỉ nhận ảnh `image/jpeg` và `image/png`.
- Folder con có MIME type `application/vnd.google-apps.folder`.
- Chỉ lấy page đầu tiên của mỗi folder.
- Không log Google Drive API key hoặc full URL có query `key`.

## Ngoài phạm vi Phase 1

- Không implement traversal tối đa 3 tầng.
- Không chọn ảnh gửi Pancake.
- Không cache/download/upload ảnh.
- Không gửi Pancake message.
- Không thêm flow fallback raw Drive link.

## File chính dự kiến sửa

- [app/services/google_drive_image_service.py](../../app/services/google_drive_image_service.py)
- [app/core/config.py](../../app/core/config.py), nếu thêm config max depth sớm.
- [tests/test_google_drive_image_service.py](../../tests/test_google_drive_image_service.py)

## Checklist

### 1. Thêm MIME type và query children

- [x] Thêm constant cho Google Drive folder MIME type `application/vnd.google-apps.folder`.
- [x] Thêm helper build query lấy JPG, PNG và folder con.
- [x] Query giữ điều kiện `'{folder_id}' in parents and trashed=false`.
- [x] Request field `nextPageToken,files(id,name,mimeType,size)`.
- [x] Validate folder id rỗng giống helper query hiện tại.

Kết quả mong muốn:
  BE có query dùng chung để lấy children của một Drive folder.

### 2. Fetch page đầu của current folder

- [x] Thêm helper fetch first page children cho một folder id.
- [x] Không truyền `pageToken` khi Google Drive trả `nextPageToken`.
- [x] Trả metadata `page_truncated=true` nếu response có `nextPageToken`.
- [x] Bỏ qua item không phải dict.
- [x] Bỏ qua item thiếu `id` ở bước convert ảnh/folder.

Kết quả mong muốn:
  Folder lớn không làm service đọc nhiều page ngoài ý muốn.

### 3. Phân loại ảnh và folder con

- [x] Convert item `image/jpeg` thành `DriveImageResult`.
- [x] Convert item `image/png` thành `DriveImageResult`.
- [x] Giữ `id`, `name`, `mimeType`, `size` cho ảnh.
- [x] Nhận diện folder con bằng MIME type Google Drive folder.
- [x] Chuẩn hóa child folder id và name để traversal phase sau dùng.
- [x] Không đưa folder con vào danh sách ảnh gửi khách.

Kết quả mong muốn:
  Service có output riêng cho ảnh và folder con từ cùng một response.

### 4. Giữ xử lý lỗi hiện tại

- [x] Timeout trả `drive_api_timeout`.
- [x] Request error trả `drive_api_request_failed`.
- [x] HTTP status `>=400` trả `drive_api_http_{status_code}`.
- [x] Invalid JSON trả `drive_api_invalid_json`.
- [x] Lỗi bất ngờ trả `drive_lookup_failed`.
- [x] Log lỗi rút gọn, không log token hoặc API key.

Kết quả mong muốn:
  Một folder lỗi không làm hỏng toàn bộ batch folder lookup.

### 5. Test phase 1

- [x] Test query children có JPG, PNG và folder MIME type.
- [x] Test fetch first page không follow `nextPageToken`.
- [x] Test `page_truncated=true` khi response có `nextPageToken`.
- [x] Test phân loại ảnh và folder con đúng.
- [x] Test bỏ qua item thiếu `id`.
- [x] Test HTTP/timeout/invalid JSON giữ behavior lỗi hiện tại.

## Acceptance criteria

- [x] Service fetch được page đầu của current folder.
- [x] Service phân loại được ảnh và folder con.
- [x] Service không gọi page 2.
- [x] Service không log API key.
- [x] Unit test phase này pass.

## Ghi chú mở

- Có thể giữ helper cũ `build_drive_files_query` để không phá test/flow cũ, và thêm helper mới cho children query.
- Nếu traversal được implement trực tiếp trong `GoogleDriveImageService`, helper page đầu vẫn nên tách nhỏ để test giới hạn pagination.
