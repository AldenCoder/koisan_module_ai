# API quản lý kho ảnh theo code

## Mục tiêu

Tạo API CRUD để upload và quản lý ảnh theo `code`.

Mỗi record có 3 trường dữ liệu nghiệp vụ:

- `code`: mã duy nhất của nhóm ảnh.
- `description`: mô tả nhóm ảnh, không bắt buộc.
- `url_images`: danh sách URL ảnh đã được lưu trên server.

Một `code` có thể chứa nhiều ảnh.

Ảnh không được lưu trực tiếp trong MongoDB. Backend nhận file upload, lưu file vào `storage/rag_images`, tạo URL truy cập ảnh, sau đó mới lưu URL vào `url_images`.

## Nguyên tắc chính

- Dùng FastAPI, Pydantic, Beanie và MongoDB theo cấu trúc hiện tại.
- Collection đề xuất là `image_assets`.
- Router đề xuất là `/api/v1/image-assets`.
- `code` là duy nhất trong toàn bộ collection.
- Client upload file ảnh, không tự gửi giá trị `url_images` khi tạo record.
- Backend là nơi tạo tên file, lưu file và sinh URL.
- Không lưu binary hoặc base64 của ảnh trong database.
- File ảnh nằm trong `storage/rag_images`.
- URL ảnh được public qua một static route riêng.
- Update dùng `PATCH`.
- Delete record đồng thời xóa các file ảnh thuộc record đó.
- API dùng cơ chế authentication và permission hiện tại.

## Luồng lưu ảnh

Luồng tạo mới:

1. Client gửi `code`, `description` nếu có và danh sách file ảnh bằng `multipart/form-data`.
2. Backend kiểm tra quyền truy cập.
3. Backend validate `code`, `description` nếu có, số lượng file, định dạng và dung lượng upload.
4. Backend decode, resize và nén từng ảnh, ưu tiên dưới 500 KB; nếu không đạt thì áp dụng giới hạn cuối từ `RAG_IMAGE_TARGET_MAX_BYTES`.
5. Backend tạo tên file theo `code` và ID ngẫu nhiên.
6. Backend lưu từng ảnh đã tối ưu vào `storage/rag_images`.
7. Backend tạo URL public tương ứng với từng file.
8. Backend lưu `code`, `description` và danh sách URL vào MongoDB.
9. Backend trả record đã tạo cho client.

Nếu lưu database thất bại sau khi file đã được ghi, backend phải xóa các file vừa tạo để không để lại file rác.

## Lưu trữ file trên server

Thư mục lưu ảnh:

- `storage/rag_images`

Backend tự tạo thư mục khi khởi động hoặc trước lần ghi file đầu tiên.

Không dùng tên file gốc làm tên lưu trực tiếp vì có thể:

- Trùng tên giữa nhiều request.
- Chứa ký tự không an toàn.
- Làm lộ tên file từ máy người dùng.
- Gây lỗi khi chạy trên hệ điều hành khác nhau.

Tên file bắt buộc có dạng:

- `{CODE}_{random_id}.jpg`

Trong đó:

- `CODE` là code đã chuẩn hóa thành chữ hoa.
- Các ký tự không an toàn trong `CODE` được thay bằng dấu gạch dưới khi dùng trong tên file.
- `random_id` là chuỗi ngẫu nhiên đủ dài để tránh trùng file.
- Phần mở rộng sau tối ưu luôn là `.jpg`.

Tên file ví dụ theo quy ước trên là `S678657_ncas77cqwbcnjcasc.jpg`.

Backend phải kiểm tra file chưa tồn tại trước khi ghi. Nếu ID ngẫu nhiên bị trùng, tạo ID mới thay vì ghi đè.

Để dễ quản lý, có thể chia file theo thư mục của record hoặc theo ngày. Phase đầu có thể lưu phẳng trong `storage/rag_images` nếu tên file luôn duy nhất.

## Resize và tối ưu ảnh

Tất cả ảnh tải lên đều phải đi qua bước decode và tối ưu trước khi lưu.

Quy tắc bắt buộc:

- Không lưu nguyên file upload vào `storage/rag_images`.
- Chuẩn hóa chiều xoay theo EXIF trước khi resize.
- Chuyển ảnh sang định dạng JPEG.
- Nếu ảnh có nền trong suốt, ghép lên nền trắng trước khi chuyển JPEG.
- Giữ đúng tỷ lệ ảnh khi resize.
- Target ưu tiên `500.000 bytes` được cố định trong code, không tạo biến môi trường riêng.
- Thử encode với JPEG quality cao, sau đó giảm quality và kích thước theo từng bước để đưa file xuống dưới 500.000 bytes.
- Nếu không thể đạt dưới 500.000 bytes theo giới hạn chất lượng và kích thước tối thiểu cho phép, dùng `RAG_IMAGE_TARGET_MAX_BYTES` làm giới hạn fallback cuối cùng.
- Với cấu hình mặc định, fallback cho phép file tối đa 1.000.000 bytes.
- Dừng tối ưu khi đã đạt dưới 500.000 bytes hoặc khi đã tạo được kết quả tốt nhất không vượt `RAG_IMAGE_TARGET_MAX_BYTES`.
- Nếu file cuối cùng vẫn vượt `RAG_IMAGE_TARGET_MAX_BYTES`, từ chối ảnh và không lưu record.

Backend nên xử lý ảnh trong memory hoặc file tạm. File tạm phải được xóa sau request, kể cả khi xử lý lỗi.

MongoDB và log có thể lưu dung lượng file sau tối ưu để phục vụ kiểm tra, nhưng không cần thêm field nghiệp vụ mới trong phase đầu.

## Public URL

Ứng dụng cần mount static route riêng để đọc ảnh từ `storage/rag_images`.

Đề xuất:

- URL public prefix: `/rag-images`
- Thư mục nguồn: `storage/rag_images`

URL hoàn chỉnh được tạo từ:

- Base URL của backend.
- Static route `/rag-images`.
- Tên file đã lưu.

Base URL nên lấy từ config, không hard-code domain production.

Config đề xuất:

- `RAG_IMAGE_STORAGE_DIR`: mặc định `storage/rag_images`.
- `RAG_IMAGE_PUBLIC_PATH`: mặc định `/rag-images`.
- `RAG_IMAGE_TARGET_MAX_BYTES`: hạn mức fallback cuối cùng khi không thể tối ưu xuống dưới target cố định 500.000 bytes, mặc định `1000000`.

Base URL tạo URL ảnh luôn lấy từ `BASE_URL`. Không có env riêng cho base URL ảnh.

Max width `2048`, max height `2048` và JPEG quality bắt đầu `90` được fix cứng trong code.

MongoDB chỉ lưu URL public đã tạo, không lưu absolute local path của server.

## Data model

Model đề xuất là `ImageAsset`, gồm:

| Field | Kiểu | Bắt buộc | Ý nghĩa |
|---|---|---:|---|
| `code` | string | Có | Mã duy nhất của nhóm ảnh |
| `description` | string hoặc null | Không | Mô tả nhóm ảnh |
| `url_images` | list string | Có | Danh sách URL ảnh đã lưu trên server |
| `created_at` | datetime | Hệ thống | Thời điểm tạo |
| `updated_at` | datetime | Hệ thống | Thời điểm cập nhật |

Index cần có:

- Unique index cho `code`.
- Index cho `updated_at` để hỗ trợ sắp xếp danh sách.

## Quy tắc validation

### `code`

- Bắt buộc khi tạo.
- Trim khoảng trắng đầu và cuối.
- Không được rỗng.
- Chuyển thành chữ hoa trước khi lưu.
- Tối đa 100 ký tự.
- Không được trùng với record khác.

Các biến thể khác nhau về chữ hoa, chữ thường hoặc khoảng trắng được xem là cùng một code.

### `description`

- Không bắt buộc khi tạo.
- Nếu được gửi lên, trim khoảng trắng đầu và cuối.
- Chuỗi rỗng sau khi trim được chuẩn hóa thành `null`.
- Tối đa 5000 ký tự.

### File ảnh

- Chỉ nhận file upload qua `multipart/form-data`.
- Chỉ chấp nhận các định dạng ảnh đã cho phép, đề xuất JPEG, PNG và WebP.
- Kiểm tra cả content type và nội dung file, không chỉ tin vào phần mở rộng.
- Từ chối file rỗng.
- Giới hạn dung lượng file upload gốc để bảo vệ memory và ổ đĩa.
- Giới hạn tổng số ảnh trong một record.
- Không cho tên file từ client quyết định đường dẫn lưu.
- Không cho phép path traversal.
- Không cho ghi đè file đang tồn tại.

Sau validation, mọi ảnh đều được chuẩn hóa thành JPEG. Backend ưu tiên tối ưu xuống dưới target cố định 500.000 bytes. Nếu không thể đạt target này, ảnh được phép lưu khi không vượt `RAG_IMAGE_TARGET_MAX_BYTES`, mặc định 1.000.000 bytes.

## API contract

### 1. Tạo nhóm ảnh

Endpoint:

- `POST /api/v1/image-assets`

Content type:

- `multipart/form-data`

Input:

- `code`
- `description`, không bắt buộc
- Một hoặc nhiều file ảnh

Permission:

- `image_assets:create`

Kết quả:

- Resize và nén tất cả ảnh, ưu tiên dưới 500 KB và fallback tối đa theo `RAG_IMAGE_TARGET_MAX_BYTES`.
- Đặt tên file theo dạng `{CODE}_{random_id}.jpg`.
- Lưu file đã tối ưu vào `storage/rag_images`.
- Tạo URL cho từng file.
- Lưu record vào MongoDB.
- Trả `201 Created`.
- Trả `409 Conflict` nếu `code` đã tồn tại.

Nếu bất kỳ file nào không hợp lệ, request bị từ chối và không lưu record.

### 2. Lấy danh sách

Endpoint:

- `GET /api/v1/image-assets`

Permission:

- `image_assets:view`

Hỗ trợ:

- Phân trang bằng `page` và `size`.
- Tìm chính xác theo `code`.
- Tìm gần đúng theo `code` hoặc `description`.
- Sắp xếp mặc định theo `updated_at` giảm dần.

Response trả các field của record, bao gồm danh sách `url_images`.

### 3. Lấy chi tiết theo ID

Endpoint:

- `GET /api/v1/image-assets/{image_asset_id}`

Permission:

- `image_assets:view`

Kết quả:

- Trả record khi tìm thấy.
- Trả `400 Bad Request` nếu ID sai format.
- Trả `404 Not Found` nếu record không tồn tại.

### 4. Lấy theo code

Endpoint:

- `GET /api/v1/image-assets/by-code/{code}`

Permission:

- `image_assets:view`

Backend chuẩn hóa `code` trước khi tìm kiếm.

Endpoint theo code phải được khai báo trước endpoint theo ID để tránh xung đột route.

### 5. Cập nhật thông tin

Endpoint:

- `PATCH /api/v1/image-assets/{image_asset_id}`

Content type:

- `multipart/form-data`

Permission:

- `image_assets:edit`

Cho phép cập nhật:

- `code`
- `description`
- Upload thêm file ảnh mới
- `remove_image_file_names`: danh sách tên file ảnh cần xóa

Quy tắc:

- Chỉ cập nhật field được gửi.
- Nếu đổi `code`, code mới không được trùng.
- Nếu đổi `code`, backend phải đổi prefix tên của toàn bộ file hiện có sang code mới và cập nhật lại toàn bộ URL trong database.
- ID ngẫu nhiên của file được giữ nguyên khi đổi code.
- Nếu rename bất kỳ file nào thất bại, rollback các file đã rename và không cập nhật database.
- File mới phải được resize, ưu tiên nén dưới 500 KB, fallback tối đa theo `RAG_IMAGE_TARGET_MAX_BYTES` và được đặt tên theo code hiện tại.
- File mới được lưu vào `storage/rag_images`, sau đó URL mới được nối vào `url_images`.
- Mỗi giá trị trong `remove_image_file_names` phải là tên file thuộc một URL hiện có trong `url_images`.
- Backend xóa các URL tương ứng khỏi `url_images` và dọn file local sau khi database cập nhật thành công.
- Có thể upload ảnh mới và xóa ảnh cũ trong cùng request.
- Danh sách ảnh sau khi cộng ảnh mới và trừ ảnh bị xóa phải còn ít nhất một ảnh.
- Không cho phép truyền absolute path hoặc tên file không thuộc record.
- Không thay thế toàn bộ ảnh cũ chỉ vì có file mới.
- Body phải có ít nhất một thay đổi.
- Cập nhật `updated_at`.

Nếu lưu database thất bại, backend phải xóa các file mới vừa upload.

### 6. Xóa nhóm ảnh

Endpoint:

- `DELETE /api/v1/image-assets/{image_asset_id}`

Permission:

- `image_assets:delete`

Luồng xử lý:

1. Tìm record.
2. Xóa record khỏi MongoDB.
3. Xóa tất cả file local được tham chiếu trong `url_images`.
4. Trả `204 No Content`.

Nếu file local đã mất, vẫn hoàn thành xóa record nhưng ghi warning log.

## Tính nhất quán giữa file và database

File system và MongoDB không có transaction chung, vì vậy service cần xử lý bù khi một bước thất bại.

### Khi create hoặc upload thêm ảnh

- Ghi file trước.
- Chỉ lưu URL vào database sau khi tất cả file hợp lệ và ghi thành công.
- Nếu database thất bại, xóa toàn bộ file vừa ghi trong request đó.

### Khi đổi code

- Chuẩn bị tên mới cho toàn bộ file theo code mới.
- Rename từng file nhưng giữ nguyên random ID.
- Chỉ cập nhật `code` và `url_images` trong database sau khi tất cả file đã rename thành công.
- Nếu rename hoặc database thất bại, đưa các file về tên cũ.

### Khi update có xóa ảnh

- Validate toàn bộ `remove_image_file_names` đều thuộc record.
- Tính danh sách ảnh cuối cùng trước khi thay đổi dữ liệu.
- Không cho update nếu kết quả không còn ảnh nào.
- Xóa URL khỏi database trong cùng lần update metadata và thêm ảnh.
- Sau khi database thành công, xóa file local.
- Nếu xóa file local thất bại, ghi warning để có thể dọn file sau.

### Khi xóa record

- Lấy trước danh sách file cần xóa.
- Xóa record khỏi database.
- Sau đó xóa các file local.
- File không tồn tại không làm request delete thất bại.

Nên có log rõ để phát hiện và dọn orphan file.

## Bảo mật

- Chỉ cho phép loại file ảnh đã cấu hình.
- Kiểm tra nội dung file thay vì chỉ kiểm tra tên.
- Tạo tên file phía server.
- Resolve và kiểm tra đường dẫn cuối cùng luôn nằm trong `storage/rag_images`.
- Không cho browse danh sách thư mục.
- Không log nội dung binary.
- Không log token hoặc thông tin xác thực.
- Có giới hạn số file và dung lượng request để tránh làm đầy ổ đĩa.
- Static route chỉ phục vụ file, không thực thi nội dung upload.

Nếu ảnh không được phép public hoàn toàn, không mount static trực tiếp; thay bằng endpoint tải ảnh có kiểm tra quyền. Phase hiện tại giả định ảnh được phép truy cập bằng URL public.

## Error response

Các status code chính:

| Status | Trường hợp |
|---:|---|
| `200` | Read hoặc update thành công |
| `201` | Create thành công |
| `204` | Delete thành công |
| `400` | ID sai format, request rỗng hoặc file không thuộc record |
| `401` | Chưa đăng nhập hoặc token không hợp lệ |
| `403` | Không có permission |
| `404` | Không tìm thấy record hoặc ảnh |
| `409` | `code` đã tồn tại |
| `415` | Định dạng file không được hỗ trợ |
| `422` | Payload không hợp lệ |
| `500` | Lỗi lưu file hoặc database không dự kiến |

Error code đề xuất:

- `IMAGE_ASSET_NOT_FOUND`
- `IMAGE_ASSET_CODE_EXISTS`
- `IMAGE_ASSET_INVALID_ID`
- `IMAGE_ASSET_EMPTY_UPDATE`
- `IMAGE_ASSET_FILE_REQUIRED`
- `IMAGE_ASSET_FILE_TYPE_NOT_ALLOWED`
- `IMAGE_ASSET_IMAGE_OPTIMIZE_FAILED`
- `IMAGE_ASSET_IMAGE_NOT_FOUND`
- `IMAGE_ASSET_STORAGE_ERROR`

## Auth và permission

Dùng các permission:

- `image_assets:view`
- `image_assets:create`
- `image_assets:edit`
- `image_assets:delete`

Khi model được thêm vào danh sách document của Beanie, cơ chế khởi tạo database hiện tại có thể tự tạo các permission trên theo tên collection.

Admin mặc định có đầy đủ quyền. Role người dùng mặc định chỉ có quyền xem theo behavior hiện tại.

## Logging

Event đề xuất:

- `IMAGE_ASSET_CREATE_SUCCESS`
- `IMAGE_ASSET_CREATE_DUPLICATE_CODE`
- `IMAGE_ASSET_FILE_SAVED`
- `IMAGE_ASSET_FILE_SAVE_FAILED`
- `IMAGE_ASSET_FILE_ROLLBACK`
- `IMAGE_ASSET_UPDATE_SUCCESS`
- `IMAGE_ASSET_IMAGE_DELETE_SUCCESS`
- `IMAGE_ASSET_IMAGE_DELETE_FAILED`
- `IMAGE_ASSET_DELETE_SUCCESS`
- `IMAGE_ASSET_ORPHAN_FILE_WARNING`

Field log an toàn:

- `image_asset_id`
- `code`
- `file_name`
- `original_file_size`
- `stored_file_size`
- `stored_width`
- `stored_height`
- `image_count`
- `current_user.email` nếu có

Không log binary file hoặc toàn bộ URL có query parameter nhạy cảm.

## Danh sách file dự kiến thay đổi khi implement

- `app/models/image_assets.py`
- `app/api/schemas/image_asset.py`
- `app/services/image_asset_service.py`
- `app/api/v1/image_assets.py`
- `app/api/router_v1.py`
- `app/core/config.py`
- `app/core/database.py`
- `app/main.py`
- `.env.example`
- `app/api/dependencies/error_codes.py`, nếu dùng error code tập trung
- `tests/test_image_assets.py`

Thư mục runtime:

- `storage/rag_images`

Thư mục ảnh runtime không commit vào Git.

## Checklist implementation tổng hợp

> Tiến độ ngày 12/06/2026: đã hoàn thành code và test local Phase 1 đến Phase 5; toàn bộ test hiện tại pass. Còn chờ kiểm chứng MongoDB, persistent volume, public HTTPS và smoke test trên staging.

Task list chi tiết từng phase:

- [Phase 1. Storage, cấu hình và public URL](image-storage-crud-api-task-list/phase-1.md)
- [Phase 2. Model, schema và database](image-storage-crud-api-task-list/phase-2.md)
- [Phase 3. Upload, resize và lưu ảnh](image-storage-crud-api-task-list/phase-3.md)
- [Phase 4. CRUD service và router](image-storage-crud-api-task-list/phase-4.md)
- [Phase 5. Test, rollout và vận hành](image-storage-crud-api-task-list/phase-5.md)

### Phase 1. Storage và static route

- [x] Thêm config thư mục, public path, base URL, số lượng, dung lượng upload và fallback tối đa 1 MB.
- [x] Khai báo target ưu tiên 500.000 bytes thành constant cố định trong code.
- [x] Tạo `storage/rag_images` khi cần.
- [x] Mount static route cho ảnh.
- [x] Tạo helper chuẩn hóa code dùng trong tên file.
- [x] Tạo helper sinh tên `{CODE}_{random_id}.jpg`.
- [x] Kiểm tra collision trước khi ghi file.
- [x] Tạo helper build public URL.
- [x] Chặn path traversal.

### Phase 2. Model và database

- [x] Tạo model `ImageAsset`.
- [x] Tạo collection `image_assets`.
- [x] Thêm unique index cho `code`.
- [x] Thêm index cho `updated_at`.
- [x] Thêm model vào danh sách Beanie.
- [ ] Xác nhận permission được tạo đúng trên MongoDB.

### Phase 3. Upload và validation

- [x] Validate `code` và `description`.
- [x] Cho phép `description` là `null` và giới hạn tối đa 5000 ký tự.
- [x] Validate request có ít nhất một ảnh.
- [x] Không giới hạn dung lượng file upload gốc ở app config; chỉ validate ảnh sau tối ưu.
- [x] Validate content type và nội dung ảnh.
- [x] Chuẩn hóa chiều xoay EXIF.
- [x] Chuyển ảnh về JPEG.
- [x] Resize giữ nguyên tỷ lệ.
- [x] Thử JPEG quality cao trước.
- [x] Giảm quality và kích thước theo từng bước để ưu tiên đạt dưới 500.000 bytes.
- [x] Fallback sang `RAG_IMAGE_TARGET_MAX_BYTES` nếu không thể đạt target 500.000 bytes.
- [x] Từ chối request nếu ảnh vẫn vượt `RAG_IMAGE_TARGET_MAX_BYTES` sau tối ưu.
- [x] Lưu file với tên do server tạo.
- [x] Dọn file tạm trong cả trường hợp thành công và lỗi.
- [x] Rollback file nếu request hoặc database thất bại.

### Phase 4. CRUD service và router

- [x] Tạo API create bằng multipart.
- [x] Tạo API list.
- [x] Tạo API detail theo ID.
- [x] Tạo API lookup theo code.
- [x] Tạo API update metadata, upload thêm ảnh và xóa ảnh cũ.
- [x] Validate `remove_image_file_names` thuộc đúng record.
- [x] Đảm bảo kết quả sau update còn ít nhất một ảnh.
- [x] Tạo API xóa record và toàn bộ file.
- [x] Gắn permission cho từng endpoint.
- [x] Register router.

### Phase 5. Test

- [x] Test upload một ảnh.
- [x] Test upload nhiều ảnh cho một code.
- [x] Test file được lưu đúng trong `storage/rag_images`.
- [x] Test tên file có dạng `{CODE}_{random_id}.jpg`.
- [x] Test code có ký tự không an toàn được chuẩn hóa trong tên file.
- [x] Test hai ảnh cùng code có tên file khác nhau.
- [x] Test URL database trỏ đúng static route.
- [x] Test code được chuẩn hóa và không trùng.
- [x] Test từ chối file không phải ảnh.
- [x] Test không còn giới hạn upload gốc ở app config.
- [x] Test ảnh JPEG ưu tiên được resize xuống dưới 500.000 bytes.
- [x] Test ảnh PNG được chuyển JPEG và ưu tiên xuống dưới 500.000 bytes.
- [x] Test ảnh WebP được chuyển JPEG và ưu tiên xuống dưới 500.000 bytes.
- [x] Test fallback chấp nhận ảnh trên 500.000 bytes nhưng không vượt `RAG_IMAGE_TARGET_MAX_BYTES`.
- [x] Test dừng tối ưu khi ảnh đã đạt dưới 500.000 bytes.
- [x] Test ảnh có EXIF orientation được xoay đúng trước khi resize.
- [x] Test ảnh có transparency được ghép nền trắng.
- [x] Test từ chối ảnh vẫn vượt `RAG_IMAGE_TARGET_MAX_BYTES` sau tối ưu.
- [x] Test từ chối quá số lượng ảnh.
- [x] Test rollback file khi database lỗi.
- [x] Test list, detail và lookup theo code.
- [x] Test update metadata.
- [x] Test create và update không truyền `description`.
- [x] Test `description` tối đa 5000 ký tự.
- [x] Test description rỗng được chuẩn hóa thành `null`.
- [x] Test đổi code rename toàn bộ file và cập nhật URL.
- [x] Test đổi code giữ nguyên random ID của từng file.
- [x] Test rollback tên file khi đổi code thất bại.
- [x] Test upload thêm ảnh không làm mất ảnh cũ.
- [x] Test update xóa một ảnh cập nhật cả database và file system.
- [x] Test update vừa thêm ảnh mới vừa xóa ảnh cũ.
- [x] Test update không xóa được ảnh không thuộc record.
- [x] Test update không được để record không còn ảnh.
- [x] Test xóa record dọn toàn bộ file.
- [x] Test permission.
- [x] Chạy `pytest -q`.

## Ghi chú production

- Cần dùng persistent volume cho `storage/rag_images`; nếu filesystem của môi trường deploy là tạm thời thì ảnh sẽ mất khi restart hoặc redeploy.
- Nếu chạy nhiều instance, local storage không được chia sẻ. Khi đó nên chuyển sang object storage như S3, MinIO hoặc dịch vụ tương đương.
- Nếu cần chặn request multipart quá lớn, cấu hình reverse proxy/infra theo chính sách triển khai.
- Nên theo dõi dung lượng ổ đĩa và số lượng orphan file.
- Backup database phải đi cùng backup thư mục ảnh.
- Domain public phải dùng HTTPS để URL ảnh hoạt động ổn định cho các dịch vụ bên ngoài.

## Tiêu chí hoàn thành

- Client upload được nhiều ảnh cho một `code`.
- File được lưu trong `storage/rag_images`.
- Tên file có dạng `{CODE}_{random_id}.jpg`.
- Mọi ảnh đều ưu tiên được tối ưu dưới 500.000 bytes và không file nào vượt `RAG_IMAGE_TARGET_MAX_BYTES`, mặc định 1.000.000 bytes.
- Backend tạo URL public sau khi lưu file thành công.
- MongoDB lưu `code`, `description` và danh sách URL.
- Có đủ create, list, detail, lookup theo code, update và xóa record.
- API update hỗ trợ thêm ảnh mới và xóa ảnh cũ trong cùng request.
- Duplicate code trả `409 Conflict`.
- File sai loại hoặc ảnh sau tối ưu vẫn vượt `RAG_IMAGE_TARGET_MAX_BYTES` bị từ chối.
- Không để lại file rác khi create hoặc update thất bại.
- Xóa ảnh và xóa record đồng bộ giữa database với file system.
- API có authentication và permission.
- Test chạy pass bằng `pytest -q`.
