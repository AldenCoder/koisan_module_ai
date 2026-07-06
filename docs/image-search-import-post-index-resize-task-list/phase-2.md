# Task List Phase 2: Implement resize thumbnail sau upsert

## Mục tiêu

Implement luồng tối ưu ảnh sau khi Chroma upsert thành công.

## Kết quả mong muốn

- [x] Thêm helper tạo thumbnail JPEG từ ảnh đã chuẩn hóa EXIF.
- [x] Ghép ảnh có alpha lên nền `#f2f2f2` trước khi encode JPEG.
- [x] Encode JPEG theo quality giảm dần.
- [x] Resize giảm dần max side cho tới khi file `<= 100000 bytes`.
- [x] Gọi helper sau khi `upsert_sources_to_chroma_index_service` thành công.
- [x] Chuẩn hóa ảnh lưu sang `.jpg` ngay từ ảnh index-ready để không rename sau upsert.
- [x] Cập nhật metadata theo file cuối cùng.
- [x] Response import trả `size_bytes`, `width`, `height` sau tối ưu.
- [x] Log bytes trước/sau tối ưu.
- [x] Giữ rollback hiện tại nếu lỗi xảy ra trước khi upsert Chroma.

## Ghi chú implement

- Chroma upsert đọc file JPEG index-ready trước khi file bị nén xuống thumbnail.
- Sau upsert, backend ghi đè nội dung file trên cùng `source_image_path`; không đổi path sau upsert để tránh Chroma metadata lệch với metadata CSV.
- Nếu input là PNG/WEBP, file public vẫn là JPEG `.jpg`.

## Acceptance Criteria

- Chroma upsert vẫn dùng ảnh index-ready.
- File public cuối cùng là thumbnail tối ưu và `<= 100000 bytes`.
- Không lưu file public lớn hơn `100000 bytes`.
- Không còn metadata trỏ tới file đã bị đổi tên hoặc xóa.
