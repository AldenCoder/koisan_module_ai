# Task List Phase 2: Fetch ảnh public và crop

## Mục tiêu

Phase 2 triển khai service tải ảnh public, validate ảnh và crop theo tọa độ tỷ lệ `0 -> 1`.

Kết quả mong muốn:

- URL public được fetch có timeout và giới hạn dung lượng.
- Ảnh được decode, chuẩn hóa orientation và crop đúng tọa độ.
- Ảnh được crop trực tiếp từ ảnh gốc trong memory và giữ format nguồn khi chuyển sang bước search.
- Lỗi fetch/crop được map về reason rõ ràng.

## Đầu vào đã chốt

- `image_url` là HTTP/HTTPS public URL.
- Crop dùng `x1`, `y1`, `x2`, `y2` dạng ratio.
- Không lưu ảnh crop vào disk.
- Content type ảnh cho phép: JPEG, PNG, WebP.

## Ngoài phạm vi Phase 2

- Chưa gọi Chroma image search.
- Chưa quyết định found/not_found.
- Chưa thay đổi Chroma index.

## File chính dự kiến sửa

- [app/services/public_image_crop_search_service.py](../../app/services/public_image_crop_search_service.py)
- [app/api/dependencies/error_codes.py](../../app/api/dependencies/error_codes.py), nếu cần thêm error code.
- [tests/test_public_image_crop_search_service.py](../../tests/test_public_image_crop_search_service.py)

## Tiến độ cập nhật

- Đã thêm service [app/services/public_image_crop_search_service.py](../../app/services/public_image_crop_search_service.py).
- Đã validate URL HTTP/HTTPS, hostname, độ dài URL và private/loopback host.
- Đã fetch ảnh bằng `httpx.AsyncClient` với timeout, redirect và max bytes.
- Đã validate content type ảnh, HTTP status, empty response và request error.
- Đã decode ảnh bằng Pillow, chuẩn hóa EXIF orientation, convert RGB và xử lý alpha.
- Đã crop ảnh gốc theo tọa độ ratio bằng floor/ceil trong memory.
- Đã có test service fetch/crop trong [tests/test_public_image_crop_search_service.py](../../tests/test_public_image_crop_search_service.py).

## Checklist

### 1. Validate URL

- [x] Chỉ nhận scheme `http`/`https`.
- [x] Reject URL thiếu hostname.
- [x] Reject URL rỗng.
- [x] Reject URL quá dài nếu cần.
- [x] Reject private/loopback host nếu bật rule SSRF.
- [x] Test URL scheme sai.
- [x] Test URL thiếu hostname.

### 2. Fetch ảnh

- [x] Dùng `httpx.AsyncClient`.
- [x] Bật `follow_redirects=True`.
- [x] Dùng timeout từ config.
- [x] Giới hạn bytes tải về.
- [x] Reject HTTP non-2xx.
- [x] Reject content type không phải ảnh.
- [x] Reject response rỗng.
- [x] Test timeout/request error.
- [x] Test HTTP non-2xx.
- [x] Test content type sai.

### 3. Decode ảnh

- [x] Decode ảnh bằng Pillow.
- [x] Chuẩn hóa EXIF orientation bằng `ImageOps.exif_transpose`.
- [x] Convert ảnh về RGB.
- [x] Composite alpha lên nền trắng với PNG/WebP trong suốt.
- [x] Reject ảnh decode lỗi.
- [x] Test JPEG hợp lệ.
- [x] Test PNG/WebP nếu dễ tạo fixture.
- [x] Test bytes không phải ảnh.

### 4. Crop ảnh

- [x] Validate `0 <= x1 < x2 <= 1`.
- [x] Validate `0 <= y1 < y2 <= 1`.
- [x] Không tự clamp tọa độ sai.
- [x] Đổi ratio sang pixel bằng floor/ceil.
- [x] Reject vùng crop quá nhỏ.
- [x] Crop ảnh đúng box.
- [x] Crop trực tiếp từ ảnh gốc và giữ format nguồn của ảnh crop.
- [x] Test crop đúng với ảnh mẫu kích thước cố định.

## Acceptance criteria

- [x] Service trả bytes ảnh crop hợp lệ.
- [x] Service không ghi ảnh ra disk.
- [x] Lỗi URL/ảnh/crop có reason rõ.
- [x] Test service fetch/crop pass.

## Ghi chú mở

- Nếu sau này cần debug crop thật, thêm feature flag riêng để lưu ảnh debug và tự dọn file.
- Nếu Pancake CDN có redirect đặc biệt, bổ sung test theo response thực tế.
