# Task List Phase 2: Cache local và download ảnh

## Mục tiêu

Phase 2 xử lý phần lưu trữ ảnh local cho Drive file link: đọc cache JSON, ưu tiên reuse `content_id` nếu đã có, kiểm tra file local, convert Drive file id thành direct download URL, download ảnh nếu thật sự cần file local, lưu ảnh vào storage và update cache an toàn.

Kết quả mong muốn:

- BE có cache JSON tại `storage/pancake_image_cache.json`.
- Nếu cache đã có `content_id` và `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true`, BE bỏ qua kiểm tra file local và không download lại từ Drive.
- BE lưu ảnh local tại `storage/pancake_images/{drive_file_id}.jpg` khi cần upload/reupload.
- File local được resize/compress về dưới `PANCAKE_IMAGE_STORAGE_MAX_BYTES`, mặc định `500000` bytes, trước khi upload Pancake.
- File đã tồn tại thì không download lại.
- File đã tồn tại nhưng vượt ngưỡng Pancake thì được tối ưu lại ngay khi cache hit.
- File đã tồn tại nhưng vượt ngưỡng và không tối ưu được thì bị bỏ để download lại từ Drive.
- Cache được update sau khi download thành công.
- Cache được ghi bằng atomic write hoặc lock để tránh hỏng file.

## Đầu vào đã chốt

- Input của phase là danh sách `drive_file_ids` hợp lệ từ Phase 1, bao gồm cả file id extract trực tiếp từ Drive file link và file id lookup từ Drive folder link.
- Direct download URL có dạng `https://drive.google.com/uc?export=download&id={drive_file_id}`.
- Google Drive có thể trả `303 See Other`; request download phải follow redirect để lấy được file ảnh thật.
- Phase đầu chỉ cần public image link download được trực tiếp.
- Chỉ chấp nhận response ảnh hợp lệ như `image/jpeg` hoặc `image/png`.
- File ghi vào `storage/pancake_images/` phải nhỏ hơn hoặc bằng `PANCAKE_IMAGE_STORAGE_MAX_BYTES`.
- `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true` cho phép coi `content_id` trong cache là đủ để gửi ảnh, không cần file local.

## Ngoài phạm vi Phase 2

- Không upload ảnh lên Pancake.
- Không gửi message có `content_ids`.
- Không quyết định lưu bot message.
- Không lookup Drive folder link ở phase này; folder đã được chuyển thành `drive_file_ids` ở Phase 1.
- Không implement cleanup storage nếu chưa có yêu cầu riêng.

## File chính dự kiến sửa

- `app/services/pancake_drive_image_service.py`
- [app/core/config.py](../../app/core/config.py)
- [.gitignore](../../.gitignore), nếu cần ignore storage.
- `tests/test_pancake_drive_image_service.py`

## Checklist

### 1. Chuẩn bị storage path

- [x] Thêm config `PANCAKE_IMAGE_CACHE_PATH`, mặc định `storage/pancake_image_cache.json`.
- [x] Thêm config `PANCAKE_IMAGE_STORAGE_DIR`, mặc định `storage/pancake_images`.
- [x] Đảm bảo thư mục `storage/pancake_images` được tạo khi cần.
- [x] Đảm bảo cache path parent folder tồn tại trước khi ghi.
- [x] Đảm bảo storage cache/images không bị commit vào git.

Kết quả mong muốn:
  Runtime có vị trí lưu cache và ảnh rõ ràng, không phụ thuộc hard-code rải rác.

### 2. Đọc cache JSON

- [x] Nếu cache JSON chưa tồn tại, khởi tạo cache rỗng.
- [x] Nếu cache JSON rỗng hoặc sai format, trả lỗi rõ ràng hoặc fallback an toàn theo quyết định.
- [x] Parse cache theo schema có `version` và `items`.
- [x] Lấy entry theo `drive_file_id`.
- [x] Nếu entry đã có `content_id` và reuse bật, trả kết quả dùng `content_id` ngay, không kiểm tra local file.
- [x] Không làm crash toàn bộ reply nếu một entry cache lỗi.

Kết quả mong muốn:
  Cache có thể đọc được ở runtime và lỗi cache có reason để debug.

### 3. Kiểm tra file local

- [x] Chỉ kiểm tra file local khi chưa có `content_id` reusable hoặc reuse đang tắt.
- [x] Build local path `storage/pancake_images/{drive_file_id}.jpg`.
- [x] Nếu file local tồn tại, bỏ qua download.
- [x] Nếu file local tồn tại nhưng size bằng 0 hoặc không đọc được, coi như cache miss.
- [x] Nếu file local tồn tại nhưng cache thiếu metadata, có thể bổ sung metadata tối thiểu.
- [x] Nếu file local tồn tại nhưng lớn hơn `PANCAKE_IMAGE_STORAGE_MAX_BYTES`, resize/compress lại trước khi trả về cho bước upload.
- [x] Nếu file local lớn hơn ngưỡng nhưng không tối ưu được, bỏ file local lỗi và download lại từ Drive.
- [x] Không trust path từ cache nếu path trỏ ra ngoài storage dir.

Kết quả mong muốn:
  Cache local tránh download lặp nhưng không mở lỗ path traversal.

### 4. Download ảnh từ Drive

- [x] Convert `drive_file_id` sang direct download URL.
- [x] Download với timeout `PANCAKE_IMAGE_DOWNLOAD_TIMEOUT_SECONDS`.
- [x] Download với `follow_redirects=True` để xử lý `303 See Other`.
- [x] Giới hạn kích thước tải về bằng `PANCAKE_IMAGE_MAX_BYTES`.
- [x] Chỉ chấp nhận content type ảnh hợp lệ.
- [x] Resize/compress ảnh về dưới `PANCAKE_IMAGE_STORAGE_MAX_BYTES` trước khi lưu local.
- [x] Convert PNG hoặc ảnh lớn về JPEG để phù hợp path `.jpg`.
- [x] Lưu file đã tối ưu vào local path sau khi download thành công.
- [x] Không lưu file lỗi hoặc response HTML/error page thành `.jpg`.
- [x] Nếu download lỗi, ghi lỗi cấp file và tiếp tục file khác.

Kết quả mong muốn:
  BE tải được ảnh public hợp lệ và bỏ qua ảnh lỗi mà không crash.

### 5. Update cache JSON

- [x] Lưu `drive_file_id`.
- [x] Lưu `drive_url` nếu còn giữ từ Phase 1.
- [x] Lưu `direct_download_url`.
- [x] Lưu `local_path`.
- [x] Lưu `downloaded_at`.
- [x] Lưu `mime_type`.
- [x] Lưu `size_bytes`.
- [x] Lưu `storage_max_bytes`, `optimized` và `original_size_bytes` khi ảnh đã được tối ưu.
- [x] Ghi cache bằng atomic write hoặc lock.

Kết quả mong muốn:
  Cache đủ metadata để debug và phục vụ phase upload.

### 6. Test phase 2

- [x] Test cache file chưa tồn tại thì khởi tạo cache rỗng.
- [x] Test cache có `content_id` và reuse bật thì không cần file local, không download Drive.
- [x] Test cache có `content_id` nhưng reuse tắt thì vẫn chuẩn bị file local để upload lại.
- [x] Test cache hit có file local thì không download lại.
- [x] Test cache hit có file local lớn hơn ngưỡng thì resize/compress lại và không download.
- [x] Test file local lớn hơn ngưỡng nhưng không đọc được thì download lại từ Drive.
- [x] Test file local rỗng thì coi là cache miss.
- [x] Test cache miss thì gọi download đúng direct download URL.
- [x] Test download được gọi với `follow_redirects=True`.
- [x] Test download thành công với ảnh lớn thì lưu file local dưới `PANCAKE_IMAGE_STORAGE_MAX_BYTES`.
- [x] Test PNG tải về được convert thành JPEG trước khi lưu local.
- [x] Test download thành công thì lưu file local.
- [x] Test download thành công thì update cache JSON.
- [x] Test content type không phải ảnh thì bỏ qua.
- [x] Test download timeout/error không crash toàn batch.
- [x] Test atomic write hoặc cơ chế ghi cache không tạo JSON hỏng trong happy path.

Kết quả mong muốn:
  Cache/download được cover bằng unit test và mock HTTP.

## Acceptance criteria

- [x] BE đọc được cache JSON.
- [x] BE bỏ qua download/local file khi cache đã có `content_id` reusable.
- [x] BE kiểm tra được file local theo `drive_file_id`.
- [x] BE bỏ qua download khi file local đã tồn tại.
- [x] BE tối ưu lại file local cũ nếu file vượt ngưỡng Pancake.
- [x] BE download và lưu ảnh khi chưa có file local.
- [x] BE chỉ lưu ảnh local đã nhỏ hơn hoặc bằng `PANCAKE_IMAGE_STORAGE_MAX_BYTES`.
- [x] BE update cache sau download thành công.
- [x] Test phase này pass.

## Ghi chú mở

- Nếu Google Drive trả trang confirm virus scan/quota, service cần reason riêng để dễ điều tra.
- Nếu thấy `drive_download_invalid_content_type` sau redirect fix, cần kiểm tra file có public thật không hoặc Google có trả HTML/confirm page không.
- Nếu ảnh PNG được lưu bằng đuôi `.jpg`, cần xác nhận có chấp nhận không; nếu không, path nên theo MIME/extension thực tế.
