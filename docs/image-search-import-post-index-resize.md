# Resize ảnh import Image Search sau khi upsert Chroma

## Mục tiêu

Tài liệu này mô tả phương án đã chốt cho `POST /api/v1/image-search-import`: ảnh upload vẫn được xử lý ở chất lượng đủ tốt để tạo foreground, crop views, embedding và upsert vào ChromaDB trước; sau khi upsert thành công, backend mới resize/nén đè file đã lưu để ảnh trong phần quản lý ảnh nhẹ hơn.

Mục tiêu chính:

- Không làm giảm chất lượng ảnh dùng để tạo embedding trong request import.
- Sau khi Chroma upsert thành công, ảnh public dùng cho UI quản lý ảnh được tối ưu như thumbnail.
- Bắt buộc ảnh lưu cuối cùng không vượt quá `100000 bytes`.
- Không thêm field API mới nếu không cần thiết; `public_url` hiện tại vẫn trỏ tới ảnh cuối cùng sau tối ưu.

Flow này triển khai theo thứ tự:

- Phần 1: giữ luồng import/index hiện tại để tạo Chroma embedding từ ảnh index-ready.
- Phần 2: resize/nén đè ảnh đã lưu sau khi Chroma upsert thành công.
- Phần 3: cập nhật metadata, response, logging và rollback cho đúng file cuối cùng.

Quy ước thuật ngữ:

- `BE` / `Backend`: repo hiện tại `koisan_module_ai`.
- `image-search-import`: endpoint `POST /api/v1/image-search-import`.
- `ảnh index-ready`: ảnh đã decode, chuẩn hóa EXIF và resize theo `CLIP_CROP_AWARE_MAX_SIDE`, dùng để tạo foreground/crop views/embedding.
- `thumbnail`: ảnh cuối cùng được lưu lại để UI quản lý ảnh hiển thị.
- `Chroma`: ChromaDB collection dùng cho crop-aware image search.
- `source_images`: thư mục `data/source_images` đang chứa ảnh import theo SKU.

## Luồng tổng thể

Client upload ảnh sản phẩm vào `POST /api/v1/image-search-import`.

Backend validate file, decode ảnh, chuẩn hóa EXIF orientation, resize ảnh theo `CLIP_CROP_AWARE_MAX_SIDE`, rồi lưu ảnh index-ready dạng JPEG chất lượng cao vào `data/source_images/{SKU}/...` để phục vụ bước index. Việc chuẩn hóa tên file `.jpg` diễn ra ngay từ bước lưu index-ready để Chroma và UI cùng dùng một `source_image_path`.

Backend ghi metadata và gọi `upsert_sources_to_chroma_index_service`. Service Chroma đọc ảnh vừa lưu, tách foreground trong memory, tạo crop-aware views, embed bằng CLIP rồi upsert vectors vào ChromaDB.

Chỉ sau khi Chroma upsert thành công, backend mới resize/nén đè nội dung file trong `data/source_images/{SKU}/...` thành ảnh thumbnail. File cuối cùng bắt buộc không vượt quá `100000 bytes`. Metadata và response trả về phải phản ánh file cuối cùng sau tối ưu: tên file, content type, dung lượng, width và height.

Nếu upsert Chroma lỗi, backend giữ rollback hiện tại: xóa file vừa lưu và xóa metadata đã append. Nếu tối ưu thumbnail lỗi sau khi Chroma đã upsert thành công, backend không được để lại metadata/response trỏ tới file public lớn hơn `100000 bytes`; cần xóa file index-ready đã lưu, log lỗi tối ưu và trả lỗi import.

## Hiện trạng hệ thống

Luồng import hiện tại nằm ở:

- [app/api/v1/image_search_import.py](../app/api/v1/image_search_import.py)
- [app/services/image_search_source_service.py](../app/services/image_search_source_service.py)
- [app/services/chroma_crop_aware_index.py](../app/services/chroma_crop_aware_index.py)
- [app/services/crop_aware_index_common.py](../app/services/crop_aware_index_common.py)
- [app/services/foreground_common.py](../app/services/foreground_common.py)

Config liên quan:

- `CLIP_CROP_AWARE_SOURCE_DIR=data/source_images`
- `CLIP_CROP_AWARE_METADATA_PATH=data/source_images_metadata.csv`
- `CLIP_CROP_AWARE_MAX_SIDE=1280`
- `CHROMA_PERSIST_DIR=data/chroma`
- `CHROMA_IMAGE_SEARCH_COLLECTION=image_search_crop_views_v1`

Trước thay đổi này, ảnh import chỉ được resize theo cạnh dài tối đa `CLIP_CROP_AWARE_MAX_SIDE`. Hàm resize cũ chỉ giới hạn kích thước pixel, chưa có target dung lượng file.

Quy tắc cũ:

- Nếu cạnh dài của ảnh lớn hơn `1280px`, resize xuống để cạnh dài bằng `1280px`.
- Nếu ảnh nhỏ hơn hoặc bằng `1280px`, giữ nguyên kích thước pixel.
- JPEG và WEBP lưu với `quality=95`.
- PNG chỉ dùng `optimize=True`.
- Không đảm bảo ảnh lưu dưới `100 KB`.

Sau implementation:

- Ảnh import được chuẩn hóa thành JPEG index-ready với `quality=95`.
- PNG/WEBP input không giữ nguyên format lưu public; file lưu trong `source_images` dùng đuôi `.jpg`.
- Sau khi upsert Chroma thành công, file cùng path được nén đè thành thumbnail `<= 100000 bytes`.

## Ranh giới trách nhiệm

### BE hiện tại

BE chịu trách nhiệm:

- Nhận file upload từ endpoint `image-search-import`.
- Validate content type, decode ảnh và chuẩn hóa EXIF orientation.
- Tạo ảnh index-ready theo `CLIP_CROP_AWARE_MAX_SIDE`.
- Lưu ảnh index-ready vào `data/source_images`.
- Ghi metadata import.
- Gọi luồng Chroma hiện tại để tạo foreground, crop views, embedding và upsert vectors.
- Sau khi upsert thành công, resize/nén đè ảnh đã lưu thành thumbnail.
- Cập nhật metadata và response theo file cuối cùng sau tối ưu.
- Log đủ thông tin debug nhưng không log raw image bytes.

### Chroma image search

Luồng Chroma hiện có chịu trách nhiệm:

- Đọc ảnh source từ metadata/path.
- Extract foreground.
- Tạo crop-aware views.
- Embed ảnh đã chuẩn bị bằng CLIP.
- Upsert vectors vào ChromaDB.

Thay đổi này không đổi thuật toán ranking, không đổi collection Chroma và không đổi logic search runtime.

### UI quản lý ảnh

UI tiếp tục dùng `public_url` hiện tại để hiển thị ảnh. Sau thay đổi, `public_url` sẽ trỏ tới ảnh đã được tối ưu như thumbnail.

## Phần 1. Giữ ảnh index-ready để upsert Chroma

Mục tiêu của phần 1 là đảm bảo embedding vẫn được tạo từ ảnh đủ chất lượng, không phải từ thumbnail đã nén mạnh.

Luồng giữ nguyên trước khi upsert:

1. Client gửi `code`, `description` và danh sách `files` dạng `multipart/form-data`.
2. Backend validate content type và đọc bytes upload.
3. Backend decode ảnh, chuẩn hóa EXIF orientation.
4. Backend resize ảnh theo `CLIP_CROP_AWARE_MAX_SIDE`.
5. Backend lưu ảnh index-ready dạng JPEG vào `data/source_images/{SKU}/{file_name}.jpg`.
6. Backend append metadata vào `data/source_images_metadata.csv`.
7. Backend gọi `upsert_sources_to_chroma_index_service`.
8. Service Chroma đọc ảnh đã lưu, extract foreground trong memory.
9. Service tạo crop-aware views.
10. Service embed views bằng CLIP.
11. Service upsert vectors vào ChromaDB.

Không được resize/nén xuống thumbnail trước bước 7.

## Phần 2. Resize/nén đè ảnh sau upsert

Mục tiêu của phần 2 là giảm dung lượng file public dùng cho UI quản lý ảnh.

Quy tắc đã chốt:

- Chỉ chạy sau khi `upsert_sources_to_chroma_index_service` thành công.
- Output cuối cùng chuẩn hóa về JPEG để dễ kiểm soát dung lượng.
- Nếu ảnh có alpha/transparency, ghép lên nền `#f2f2f2` trước khi lưu JPEG.
- Target dung lượng bắt buộc: `<= 100000 bytes`.
- Max side khởi điểm: `512px`.
- JPEG quality khởi điểm: `85`.
- Giảm quality theo các mức: `85`, `80`, `75`, `70`, `65`, `60`, `55`, `50`, `45`.
- Nếu vẫn lớn hơn target, giảm max side theo các mức: `448`, `384`, `320`, `256`, `224`, `192`, `160`, `128`, `96`, sau đó tiếp tục giảm xuống các mức nhỏ hơn nếu cần để đảm bảo target.
- Dừng khi ảnh nhỏ hơn hoặc bằng `100000 bytes`.
- Không lưu bản lớn hơn `100000 bytes`.

Về kỹ thuật có thể ép mọi ảnh về dưới `100000 bytes` bằng cách giảm tiếp kích thước pixel. Trade-off là với ảnh quá phức tạp, thumbnail cuối cùng có thể nhỏ hơn và chất lượng thấp hơn, nhưng vẫn đủ cho mục tiêu hiển thị dạng thumbnail.

Nếu file gốc là PNG hoặc WEBP, backend chuẩn hóa file lưu sang `.jpg` ngay từ ảnh index-ready. Sau upsert chỉ ghi đè nội dung thumbnail trên cùng path, tránh trường hợp Chroma giữ `source_image_path` cũ còn metadata/response trỏ sang file mới.

## Phần 3. Metadata, response và rollback

Metadata và response phải phản ánh file cuối cùng sau tối ưu:

- `file_name`
- `source_image_path`
- `public_url`
- `content_type`
- `size_bytes`
- `width`
- `height`

Thứ tự xử lý lỗi:

1. Nếu validate upload lỗi, không lưu file.
2. Nếu lưu ảnh index-ready lỗi, không ghi metadata.
3. Nếu ghi metadata lỗi, xóa file vừa lưu.
4. Nếu upsert Chroma lỗi, rollback metadata và xóa file vừa lưu như hiện tại.
5. Nếu tối ưu thumbnail lỗi sau khi upsert thành công:
   - Không rollback Chroma.
   - Không được ghi metadata/response trỏ tới file lớn hơn `100000 bytes`.
   - Xóa file index-ready đã lưu nếu không tạo được thumbnail hợp lệ.
   - Log lỗi thumbnail optimization.
   - Trả lỗi import để caller biết ảnh chưa được lưu thành công cho phần quản lý.

Policy chốt: ảnh public cuối cùng phải `<= 100000 bytes`. Không giữ file lớn hơn target chỉ vì Chroma đã upsert thành công.

## Tác động API

- Không đổi endpoint.
- Không đổi request body.
- Không thêm field response mới.
- `public_url` vẫn là field UI dùng để hiển thị ảnh.
- `size_bytes`, `width`, `height` là thông tin file cuối cùng sau tối ưu.
- Nếu file cuối cùng chuyển sang JPEG, `content_type` nên là `image/jpeg`.

## Danh sách file dự kiến thay đổi khi implement

- [app/services/image_search_source_service.py](../app/services/image_search_source_service.py)
  - Thêm helper optimize thumbnail.
  - Gọi optimize sau khi `upsert_sources_to_chroma_index_service` thành công.
  - Cập nhật metadata sau khi file cuối cùng thay đổi.
  - Đảm bảo rollback file/metadata đúng nếu lỗi trước upsert.
- [tests/test_image_search_source_service.py](../tests/test_image_search_source_service.py)
  - Test ảnh import lớn được upsert bằng ảnh index-ready trước khi tối ưu.
  - Test file cuối cùng luôn nhỏ hơn hoặc bằng target.
  - Test metadata trả về kích thước/dung lượng sau tối ưu.
  - Test upsert lỗi thì không giữ file rác.
  - Test tối ưu thumbnail lỗi thì không để lại file public lớn hơn target.

## Checklist implementation tổng hợp

Trạng thái hiện tại: đã implement resize/nén đè ảnh source sau khi Chroma upsert thành công. Targeted test cho `tests/test_image_search_source_service.py` đã pass; full suite `pytest -q` đã pass.

### Phase 1. Chốt contract và thứ tự xử lý

- [x] Chốt chỉ dùng một phương án: resize đè sau khi upsert Chroma.
- [x] Chốt không tạo URL thumbnail riêng.
- [x] Chốt không đổi request body.
- [x] Chốt không đổi response schema.
- [x] Chốt `public_url` trỏ tới file cuối cùng sau tối ưu.
- [x] Chốt không resize xuống thumbnail trước khi upsert Chroma.
- [x] Chốt target thumbnail bắt buộc `<= 100000 bytes`.
- [x] Chốt max side thumbnail khởi điểm `512px`.
- [x] Chốt JPEG quality floor ban đầu `45`, sau đó giảm pixel tiếp nếu cần.
- [x] Chốt không lưu file public lớn hơn `100000 bytes`.

### Phase 2. Implement optimize thumbnail

- [x] Thêm helper tạo thumbnail JPEG từ ảnh đã chuẩn hóa EXIF.
- [x] Ghép ảnh có alpha lên nền `#f2f2f2` trước khi encode JPEG.
- [x] Encode JPEG theo quality giảm dần.
- [x] Resize giảm dần max side cho tới khi file `<= 100000 bytes`.
- [x] Gọi helper sau khi `upsert_sources_to_chroma_index_service` thành công.
- [x] Chuẩn hóa file lưu sang `.jpg` ngay từ ảnh index-ready để không phải rename sau upsert.
- [x] Cập nhật metadata theo file cuối cùng.
- [x] Log bytes trước/sau tối ưu.

### Phase 3. Test và rollout

- [x] Test ảnh lớn được resize index-ready theo `CLIP_CROP_AWARE_MAX_SIDE` trước khi upsert.
- [x] Test Chroma upsert nhận đúng path ảnh index-ready.
- [x] Test sau upsert file cuối cùng luôn nhỏ hơn hoặc bằng `100000 bytes`.
- [x] Test metadata sau import phản ánh đúng file cuối cùng.
- [x] Test PNG có alpha được ghép nền trước khi chuyển JPEG.
- [x] Test upsert Chroma lỗi thì rollback metadata và xóa file mới.
- [x] Test tối ưu thumbnail lỗi thì không để lại file public lớn hơn target.
- [x] Chạy targeted tests.
- [x] Chạy `pytest -q`.

Task list chi tiết từng phase:

- [Phase 1. Chốt contract và thứ tự xử lý](image-search-import-post-index-resize-task-list/phase-1.md)
- [Phase 2. Implement resize thumbnail sau upsert](image-search-import-post-index-resize-task-list/phase-2.md)
- [Phase 3. Test và rollout](image-search-import-post-index-resize-task-list/phase-3.md)

## Test cần có khi implement

- Import ảnh vẫn tạo embedding từ ảnh index-ready.
- Không gọi optimize thumbnail trước khi upsert Chroma.
- Thumbnail output là JPEG.
- PNG/WebP có alpha được ghép nền `#f2f2f2`.
- File cuối cùng luôn nhỏ hơn hoặc bằng `100000 bytes`.
- Metadata trả đúng `file_name`, `source_image_path`, `size_bytes`, `width`, `height`.
- Response trả đúng thông tin file cuối cùng.
- Upsert Chroma lỗi thì rollback metadata và xóa file.
- Optimize thumbnail lỗi thì không để lại file public lớn hơn target.

## Ghi chú production

- Nên backup hoặc snapshot volume `data` trước khi bật logic mới trên production.
- Nên import thử một SKU mới và kiểm tra search bằng chính ảnh đó.
- Nên kiểm tra ảnh trong màn quản lý tải đúng URL và dung lượng đã giảm.
- Nên theo dõi log tối ưu ảnh trong vài ngày đầu để biết ảnh bị giảm xuống mức pixel/quality nào mới đạt `100000 bytes`.
- Không thay đổi threshold search, crop views hoặc Chroma collection trong task này.
