# Task List Phase 3: Upload, resize và lưu ảnh

## Mục tiêu

Phase 3 xây dựng pipeline nhận file upload, xác thực ảnh, chuẩn hóa về JPEG, tối ưu dung lượng, đặt tên theo code và lưu vào `storage/rag_images`. Pipeline phải rollback file nếu bất kỳ bước nào thất bại.

Kết quả mong muốn:

- Backend nhận được JPEG, PNG và WebP.
- File giả ảnh hoặc ảnh lỗi bị reject.
- Ảnh được xoay đúng theo EXIF.
- Ảnh transparency được ghép nền trắng.
- Ảnh được ưu tiên tối ưu dưới 500.000 bytes.
- Nếu không đạt 500 KB, ảnh vẫn được chấp nhận khi không vượt `RAG_IMAGE_TARGET_MAX_BYTES`.
- File lưu có dạng `{CODE}_{random_id}.jpg`.
- Không còn file tạm hoặc file rác sau lỗi.

## Đầu vào đã chốt

- Upload dùng `multipart/form-data`.
- Một request có thể chứa nhiều file.
- Chỉ hỗ trợ JPEG, PNG và WebP trong phase đầu.
- Tất cả file lưu cuối cùng là JPEG.
- Target ưu tiên 500.000 bytes là constant trong code.
- Fallback mặc định là `RAG_IMAGE_TARGET_MAX_BYTES=1000000`.
- Dùng Pillow hiện có trong project.
- Phải giữ tỷ lệ ảnh khi resize.
- Không lưu nguyên binary upload vào MongoDB.

## Ngoài phạm vi Phase 3

- Chưa tạo endpoint list/detail/delete.
- Chưa update MongoDB record hoàn chỉnh.
- Chưa đổi code và rename ảnh cũ.
- Chưa xóa ảnh cũ qua API update.
- Không tạo thumbnail riêng.
- Không hỗ trợ GIF động, SVG, HEIC hoặc video.

## File chính dự kiến sửa

- `app/services/image_asset_service.py`
- [app/core/config.py](../../app/core/config.py)
- `tests/test_image_asset_service.py`
- `tests/test_image_asset_image_processing.py`

## Checklist

> Trạng thái: Hoàn thành implementation và unit test ngày 12/06/2026.

### 1. Đọc upload an toàn

- [x] Đọc upload từ `UploadFile` và đóng file sau xử lý; app không đặt giới hạn dung lượng upload gốc.
- [x] Reject file rỗng.
- [x] Đảm bảo đóng `UploadFile` sau xử lý.
- [x] Dọn file tạm nếu dùng spool/temp file.
- [x] Không log binary.

Kết quả mong muốn:
  File rỗng hoặc sai loại bị chặn; dung lượng upload gốc không bị giới hạn ở app config.

### 2. Xác thực định dạng ảnh

- [x] Kiểm tra content type được phép.
- [x] Dùng Pillow decode nội dung thật.
- [x] Verify ảnh không bị truncate hoặc corrupt theo rule đã chọn.
- [x] Không tin extension hoặc filename từ client.
- [x] Reject HTML, text hoặc binary giả content type ảnh.
- [x] Reject format ngoài JPEG, PNG, WebP.
- [x] Map lỗi decode thành error code an toàn.

Kết quả mong muốn:
  Chỉ nội dung ảnh thật đi tiếp vào pipeline tối ưu.

### 3. Chuẩn hóa orientation và màu

- [x] Đọc EXIF orientation.
- [x] Xoay/lật ảnh đúng trước khi resize.
- [x] Loại metadata EXIF khỏi file output nếu không cần.
- [x] Chuyển ảnh grayscale hoặc palette về mode phù hợp với JPEG.
- [x] Với ảnh RGBA/transparency, ghép lên nền trắng.
- [x] Không tạo nền đen ngoài ý muốn.
- [x] Giữ đúng tỷ lệ và nội dung nhìn thấy.

Kết quả mong muốn:
  File JPEG đầu ra hiển thị đúng chiều và màu nền dự kiến.

### 4. Chốt thuật toán tối ưu dung lượng

- [x] Khai báo constant target ưu tiên là 500.000 bytes.
- [x] Lấy hard limit fallback từ `RAG_IMAGE_TARGET_MAX_BYTES`.
- [x] Validate hard limit không nhỏ hơn target ưu tiên.
- [x] Encode JPEG quality cao trước.
- [x] Nếu output vượt target, giảm quality theo các bước có giới hạn.
- [x] Nếu giảm quality chưa đủ, giảm dimensions theo tỷ lệ.
- [x] Không upscale ảnh nhỏ.
- [x] Đặt quality tối thiểu để tránh ảnh mất khả năng sử dụng.
- [x] Đặt dimensions tối thiểu để tránh thu ảnh quá nhỏ.
- [x] Theo dõi candidate tốt nhất dưới hard limit trong quá trình tối ưu.
- [x] Dừng ngay khi đạt dưới target 500.000 bytes.
- [x] Nếu không đạt target, dùng candidate chất lượng tốt nhất không vượt hard limit.
- [x] Nếu không có candidate dưới hard limit, reject ảnh.

Kết quả mong muốn:
  Pipeline ưu tiên 500 KB nhưng không làm giảm chất lượng vô hạn chỉ để đạt target.

### 5. Lưu file cuối cùng

- [x] Sinh filename bằng helper Phase 1.
- [x] Filename dùng code đã normalize.
- [x] File output luôn có extension `.jpg`.
- [x] Chỉ ghi candidate đã xác nhận không vượt hard limit.
- [x] Ghi file theo cách tránh để lại file nửa chừng.
- [x] Nếu dùng file tạm, rename/move atomically vào path cuối.
- [x] Không overwrite file hiện có.
- [x] Xác nhận file đã ghi có size bằng candidate.
- [x] Trả metadata gồm filename, local path, public URL, original size, stored size, width, height.

Kết quả mong muốn:
  Service trả đủ thông tin để phase CRUD cập nhật database và logging.

### 6. Xử lý batch nhiều ảnh

- [x] Validate số lượng toàn batch trước khi ghi.
- [x] Validate từng ảnh trước hoặc rollback toàn batch nếu một ảnh lỗi.
- [x] Chốt behavior atomic: một ảnh lỗi thì cả request create/update lỗi.
- [x] Theo dõi danh sách file đã ghi trong request.
- [x] Nếu ảnh thứ N lỗi, xóa file 1 đến N-1 đã ghi.
- [x] Không xóa file cũ của record trong rollback upload mới.
- [x] Giữ thứ tự URL theo thứ tự file client gửi.

Kết quả mong muốn:
  Batch upload không tạo record hoặc file dở dang.

### 7. Logging

- [x] Log filename đã lưu.
- [x] Log code.
- [x] Log original size.
- [x] Log stored size.
- [x] Log width và height cuối.
- [x] Log có đạt target 500 KB hay dùng fallback.
- [x] Log reason khi optimize thất bại.
- [x] Không log binary hoặc nội dung EXIF.
- [x] Không log absolute storage path nếu không cần.

Kết quả mong muốn:
  Có thể điều tra chất lượng tối ưu mà không lộ dữ liệu không cần thiết.

### 8. Test Phase 3

- [x] Test upload JPEG hợp lệ.
- [x] Test upload PNG hợp lệ.
- [x] Test upload WebP hợp lệ.
- [x] Test reject file rỗng.
- [x] Test reject content type không hỗ trợ.
- [x] Test reject file giả ảnh.
- [x] Test reject ảnh corrupt.
- [x] Test EXIF orientation.
- [x] Test transparency được ghép nền trắng.
- [x] Test output luôn là JPEG.
- [x] Test filename đúng code và random ID.
- [x] Test ảnh lớn được tối ưu dưới 500.000 bytes khi có thể.
- [x] Test fallback chấp nhận candidate trên 500.000 bytes nhưng dưới hard limit.
- [x] Test reject khi mọi candidate đều vượt hard limit.
- [x] Test không upscale ảnh nhỏ.
- [x] Test output giữ tỷ lệ.
- [x] Test batch nhiều ảnh giữ thứ tự.
- [x] Test batch rollback toàn bộ file khi một ảnh lỗi.
- [x] Test dọn file tạm sau success và failure.

Kết quả mong muốn:
  Pipeline ảnh được test độc lập, không cần MongoDB hoặc external service.

## Acceptance criteria

- [x] JPEG, PNG, WebP được xử lý.
- [x] File output luôn là JPEG.
- [x] Target 500 KB được ưu tiên.
- [x] File output không vượt `RAG_IMAGE_TARGET_MAX_BYTES`.
- [x] Filename đúng `{CODE}_{random_id}.jpg`.
- [x] Batch upload rollback đúng khi lỗi.
- [x] Không để lại file tạm.
- [x] Test Phase 3 pass.

## Ghi chú mở

- Không nên giảm quality hoặc dimensions đến mức thấp nhất chỉ để đạt 500 KB; hard limit 1 MB là vùng fallback nhằm giữ ảnh còn đủ chi tiết cho RAG hoặc nghiệp vụ phía sau.
- Nếu ảnh panorama hoặc ảnh có dimensions đặc biệt thường xuyên vượt hard limit, cần quan sát dữ liệu thật trước khi đổi thuật toán.
