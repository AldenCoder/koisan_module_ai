# Task List Phase 4: CRUD service và router

## Mục tiêu

Phase 4 triển khai đầy đủ API CRUD cho `ImageAsset`, nối model MongoDB với pipeline file của Phase 3. Trọng tâm là giữ nhất quán giữa database và filesystem khi create, update, đổi code, thêm ảnh, xóa ảnh hoặc xóa toàn bộ record.

Kết quả mong muốn:

- Có API create, list, detail, lookup theo code, update và delete.
- Create lưu file trước rồi tạo record.
- Update hỗ trợ đồng thời sửa metadata, thêm ảnh và xóa ảnh.
- Đổi code rename file hiện có và cập nhật URL.
- Delete record xóa database và dọn toàn bộ file.
- Duplicate code trả `409`.
- Mọi endpoint có permission phù hợp.

## Đầu vào đã chốt

- Prefix router là `/api/v1/image-assets`.
- Create và update dùng `multipart/form-data`.
- `description` không bắt buộc, tối đa 5000 ký tự.
- `remove_image_file_names` nằm trong API update, không tạo API xóa từng ảnh riêng.
- Sau update record phải còn ít nhất một ảnh.
- Xóa nhóm ảnh dùng endpoint delete record.
- File system và MongoDB không có transaction chung; service phải có rollback/compensation.

## Ngoài phạm vi Phase 4

- Không tạo UI quản lý ảnh.
- Không upload trực tiếp lên S3/MinIO.
- Không soft delete.
- Không lưu audit history.
- Không cho client nhập URL ảnh bên ngoài.
- Không tạo API xóa ảnh riêng.

## File chính dự kiến sửa

- `app/services/image_asset_service.py`
- `app/api/v1/image_assets.py`
- [app/api/router_v1.py](../../app/api/router_v1.py)
- `app/api/schemas/image_asset.py`
- [app/api/dependencies/error_codes.py](../../app/api/dependencies/error_codes.py), nếu dùng error code tập trung.
- `tests/test_image_assets.py`
- `tests/test_image_asset_service.py`

## Checklist

> Trạng thái: Hoàn thành implementation và test local ngày 12/06/2026.

### 1. Service serialize và lookup chung

- [x] Tạo serializer dùng chung cho response.
- [x] Convert document ID thành string.
- [x] Trả `description=None` đúng contract.
- [x] Trả `url_images` theo đúng thứ tự lưu.
- [x] Normalize datetime theo convention hiện tại.
- [x] Tạo helper parse và validate ObjectId.
- [x] Tạo helper lấy record theo ID.
- [x] Tạo helper lấy record theo code đã normalize.
- [x] Không lặp logic not-found ở nhiều endpoint.

Kết quả mong muốn:
  CRUD dùng chung cách lookup và response, giảm sai khác contract.

### 2. Create service

- [x] Nhận `code`, optional `description` và danh sách upload.
- [x] Normalize metadata trước khi xử lý file.
- [x] Kiểm tra code tồn tại để trả lỗi sớm.
- [x] Validate có ít nhất một file.
- [x] Gọi pipeline Phase 3 cho toàn bộ file.
- [x] Tạo `url_images` từ kết quả file đã lưu.
- [x] Insert `ImageAsset` sau khi tất cả file được ghi thành công.
- [x] Bắt `DuplicateKeyError` do race condition.
- [x] Nếu insert thất bại, xóa toàn bộ file vừa tạo.
- [x] Không xóa file của request khác khi rollback.
- [x] Trả record đã insert.

Kết quả mong muốn:
  Create là atomic ở mức nghiệp vụ: hoặc có cả record và file, hoặc không còn gì.

### 3. List service

- [x] Hỗ trợ `page >= 1`.
- [x] Hỗ trợ `size` từ 1 đến 100.
- [x] Filter chính xác theo code đã normalize.
- [x] Search keyword trong `code` hoặc `description`.
- [x] Escape keyword trước khi tạo regex.
- [x] Không đưa raw regex từ client vào query.
- [x] Sort `updated_at` giảm dần.
- [x] Tính `total`.
- [x] Trả `items`, `total`, `page`, `size`.
- [x] Description null không làm search/list lỗi.

Kết quả mong muốn:
  List có pagination và search an toàn.

### 4. Detail và lookup theo code

- [x] Tạo detail theo `image_asset_id`.
- [x] ID sai format trả `400`.
- [x] ID hợp lệ nhưng không tồn tại trả `404`.
- [x] Tạo lookup theo `code`.
- [x] Normalize code trước khi query.
- [x] Code không tồn tại trả `404`.
- [x] Khai báo route `/by-code/{code}` trước route `/{image_asset_id}`.

Kết quả mong muốn:
  Client lấy được record bằng MongoDB ID hoặc business code.

### 5. Validate update tổng hợp

- [x] Load record hiện tại trước khi xử lý file.
- [x] Xác định field nào thực sự được gửi.
- [x] Reject request không có thay đổi.
- [x] Normalize code mới nếu có.
- [x] Normalize description nếu có.
- [x] Description rỗng chủ động clear thành `null`.
- [x] Deduplicate `remove_image_file_names`.
- [x] Xác nhận từng filename cần xóa thuộc record hiện tại.
- [x] Reject filename không thuộc record.
- [x] Reject absolute path hoặc path separator.
- [x] Tính số ảnh cuối cùng: ảnh cũ trừ ảnh xóa cộng ảnh mới.
- [x] Reject nếu kết quả cuối không còn ảnh.

Kết quả mong muốn:
  Toàn bộ update được validate trước khi bắt đầu thay đổi filesystem.

### 6. Chuẩn bị update filesystem

- [x] Nếu có file mới, xử lý file mới bằng code cuối cùng của record.
- [x] Theo dõi toàn bộ file mới để rollback.
- [x] Nếu đổi code, chỉ rename các file cũ được giữ lại.
- [x] File nằm trong `remove_image_file_names` không cần rename.
- [x] Khi rename, giữ nguyên random ID và đổi prefix code.
- [x] Kiểm tra destination không tồn tại.
- [x] Theo dõi mapping old path sang new path.
- [x] Nếu một rename thất bại, rollback các rename trước đó.
- [x] Nếu rename thất bại, xóa file mới vừa upload.
- [x] Chưa xóa file cũ được yêu cầu remove trước khi database update thành công.

Kết quả mong muốn:
  Trước khi save database, service có trạng thái file mới hoàn chỉnh và vẫn có thể rollback.

### 7. Save update database

- [x] Build danh sách URL cuối cùng theo đúng thứ tự.
- [x] Loại URL của ảnh cần xóa.
- [x] Thay URL file rename bằng URL mới.
- [x] Nối URL ảnh upload mới vào cuối danh sách.
- [x] Set code mới nếu có.
- [x] Set description mới nếu có.
- [x] Set `updated_at`.
- [x] Save document một lần sau khi filesystem preparation thành công.
- [x] Bắt duplicate code và trả `409`.
- [x] Nếu save lỗi, rollback rename về tên cũ.
- [x] Nếu save lỗi, xóa file upload mới.
- [x] Nếu rollback lỗi, ghi critical/error log đủ metadata để xử lý thủ công.

Kết quả mong muốn:
  Database chỉ trỏ tới file đã tồn tại và URL đúng code hiện tại.

### 8. Hoàn tất xóa ảnh sau update

- [x] Chỉ xóa file trong `remove_image_file_names` sau khi database save thành công.
- [x] Resolve từng path trong storage root.
- [x] File đã mất không làm update thất bại.
- [x] File xóa lỗi được warning log.
- [x] Không rollback database chỉ vì cleanup file cũ thất bại.
- [x] Log orphan file để có thể dọn sau.
- [x] Trả record mới sau update.

Kết quả mong muốn:
  Update thành công về dữ liệu; lỗi cleanup không làm mất trạng thái DB đã đúng.

### 9. Delete record service

- [x] Load record và lấy trước danh sách filename.
- [x] ID sai format trả `400`.
- [x] Record không tồn tại trả `404`.
- [x] Xóa document khỏi MongoDB.
- [x] Sau khi database thành công, xóa từng file local.
- [x] File không tồn tại không làm delete thất bại.
- [x] File cleanup lỗi được warning log.
- [x] Trả `204 No Content`.
- [x] Gọi delete lần hai trả `404`.

Kết quả mong muốn:
  Xóa nhóm ảnh loại record khỏi hệ thống và cố gắng dọn toàn bộ storage liên quan.

### 10. Router create

- [x] Tạo `POST /api/v1/image-assets`.
- [x] Nhận multipart `code`.
- [x] Nhận multipart optional `description`.
- [x] Nhận một hoặc nhiều file.
- [x] Gắn permission `image_assets:create`.
- [x] Trả response model thống nhất.
- [x] Trả `201 Created`.
- [x] Không expose exception filesystem hoặc MongoDB thô.

Kết quả mong muốn:
  Client tạo được một nhóm ảnh hoàn chỉnh bằng multipart.

### 11. Router read

- [x] Tạo `GET /api/v1/image-assets`.
- [x] Gắn permission `image_assets:view`.
- [x] Khai báo query `page`, `size`, `code`, `keyword`.
- [x] Tạo `GET /api/v1/image-assets/by-code/{code}`.
- [x] Tạo `GET /api/v1/image-assets/{image_asset_id}`.
- [x] Đảm bảo route order không xung đột.
- [x] Trả đúng status `400` và `404`.

Kết quả mong muốn:
  Các API read có contract rõ và dùng chung permission view.

### 12. Router update

- [x] Tạo `PATCH /api/v1/image-assets/{image_asset_id}`.
- [x] Nhận optional `code`.
- [x] Nhận optional `description`.
- [x] Nhận optional danh sách file mới.
- [x] Nhận optional `remove_image_file_names`.
- [x] Chốt cách client gửi nhiều filename trong multipart.
- [x] Gắn permission `image_assets:edit`.
- [x] Trả record sau update.
- [x] Không tạo endpoint delete một ảnh riêng.

Kết quả mong muốn:
  Một endpoint update xử lý được toàn bộ thay đổi cấp record.

### 13. Router delete và register

- [x] Tạo `DELETE /api/v1/image-assets/{image_asset_id}`.
- [x] Gắn permission `image_assets:delete`.
- [x] Trả `204 No Content`.
- [x] Import router trong `app/api/router_v1.py`.
- [x] Register prefix `/image-assets`.
- [x] Tag OpenAPI rõ ràng.
- [x] Xác nhận route có prefix cuối `/api/v1/image-assets`.

Kết quả mong muốn:
  CRUD được expose đầy đủ qua router v1.

### 14. Logging

- [x] Log create success với code, ID, image count.
- [x] Log duplicate code.
- [x] Log list với filter và pagination rút gọn.
- [x] Log update gồm số ảnh thêm và số ảnh xóa.
- [x] Log code rename.
- [x] Log rollback file mới.
- [x] Log rollback rename.
- [x] Log delete record.
- [x] Log cleanup file thất bại.
- [x] Không log binary hoặc token.

Kết quả mong muốn:
  Có đủ dấu vết để điều tra mismatch database/filesystem.

## Acceptance criteria

- [x] Create hoạt động và rollback khi insert lỗi.
- [x] List/detail/by-code hoạt động.
- [x] Update sửa metadata được.
- [x] Update thêm và xóa ảnh trong cùng request được.
- [x] Update đổi code rename file và URL đúng.
- [x] Update không thể để record rỗng ảnh.
- [x] Delete xóa record và cleanup file.
- [x] Permission đúng cho mọi endpoint.
- [x] Router v1 được register.

## Ghi chú mở

- Cleanup file sau khi database thành công là best effort. Nếu cần đảm bảo mạnh hơn, có thể bổ sung bảng/file queue cleanup ở task sau.
- Khi đổi code cùng lúc với xóa ảnh, `remove_image_file_names` được hiểu theo tên file hiện tại trước update.
