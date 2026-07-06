# Task List Phase 2: Model, schema và database

## Mục tiêu

Phase 2 tạo model `ImageAsset`, các schema request/response và đăng ký collection với Beanie. Phase này chốt contract dữ liệu `code`, `description`, `url_images` trước khi triển khai upload và CRUD.

Kết quả mong muốn:

- MongoDB có collection `image_assets`.
- `code` có unique index.
- `description` optional, tối đa 5000 ký tự.
- `url_images` lưu danh sách URL public của ảnh.
- Response trả đúng ID và timestamps.
- Permission CRUD được tạo theo cơ chế hiện tại.

## Đầu vào đã chốt

- Model tên `ImageAsset`.
- Collection tên `image_assets`.
- `code` bắt buộc, duy nhất, tối đa 100 ký tự.
- `description` không bắt buộc, tối đa 5000 ký tự.
- Description rỗng sau trim được lưu thành `null`.
- `url_images` có ít nhất một URL.
- Client không tự gửi `url_images`; backend tạo field này từ file đã lưu.
- Record có `created_at` và `updated_at`.

## Ngoài phạm vi Phase 2

- Chưa ghi file vào storage.
- Chưa resize hoặc nén ảnh.
- Chưa tạo CRUD endpoint hoàn chỉnh.
- Chưa implement rollback filesystem.
- Chưa mount static route nếu Phase 1 chưa hoàn thành.

## File chính dự kiến sửa

- `app/models/image_assets.py`
- `app/api/schemas/image_asset.py`
- [app/core/database.py](../../app/core/database.py)
- [app/api/dependencies/error_codes.py](../../app/api/dependencies/error_codes.py), nếu dùng error code tập trung.
- `tests/test_image_asset_model.py`
- `tests/test_image_asset_schema.py`

## Checklist

> Trạng thái: Hoàn thành implementation và unit test ngày 12/06/2026. Còn chờ xác nhận index và role/permission trên MongoDB thật khi triển khai Phase 4.

### 1. Tạo model `ImageAsset`

- [x] Tạo Beanie document mới.
- [x] Khai báo `code` bắt buộc.
- [x] Giới hạn `code` tối đa 100 ký tự.
- [x] Khai báo `description` optional.
- [x] Giới hạn `description` tối đa 5000 ký tự.
- [x] Khai báo `url_images` là danh sách string.
- [x] Yêu cầu `url_images` có ít nhất một item.
- [x] Thêm `created_at` bằng `now_vn`.
- [x] Thêm `updated_at` bằng `now_vn`.
- [x] Đặt collection name là `image_assets`.

Kết quả mong muốn:
  Document phản ánh đúng ba field nghiệp vụ và metadata hệ thống.

### 2. Index database

- [x] Tạo unique index cho `code`.
- [x] Đặt tên index rõ ràng.
- [x] Tạo index cho `updated_at`.
- [x] Không tạo index cho `description`.
- [x] Không tạo index cho từng item trong `url_images` nếu chưa có use case tìm theo URL.
- [ ] Xác nhận startup tạo index thành công trên database rỗng.
- [x] Ghi chú cách xử lý nếu production đã có code trùng trước khi tạo unique index.

Kết quả mong muốn:
  Database bảo vệ duplicate code kể cả khi có request đồng thời.

### 3. Đăng ký model với Beanie

- [x] Import `ImageAsset` trong `app/core/database.py`.
- [x] Thêm model vào `DOCUMENT_MODELS`.
- [x] Xác nhận `init_beanie` nhận model mới.
- [x] Xác nhận cơ chế `_ensure_default_permissions` tạo quyền theo collection.
- [ ] Xác nhận admin role nhận quyền mới.
- [ ] Xác nhận role mặc định chỉ nhận quyền view theo behavior hiện tại.

Kết quả mong muốn:
  Model được khởi tạo và permission được đồng bộ khi app startup.

### 4. Schema response

- [x] Tạo schema item/detail response.
- [x] Response có `id`.
- [x] Response có `code`.
- [x] Response có `description` nullable.
- [x] Response có `url_images`.
- [x] Response có `created_at`.
- [x] Response có `updated_at`.
- [x] Tạo schema list có `items`, `total`, `page`, `size`.
- [x] Đảm bảo datetime serialize nhất quán với các API hiện tại.

Kết quả mong muốn:
  Create, detail, update và list có response contract dùng chung.

### 5. Schema input metadata

- [x] Tạo validation dùng chung cho code.
- [x] Trim code.
- [x] Chuyển code thành chữ hoa.
- [x] Reject code rỗng sau trim.
- [x] Tạo validation dùng chung cho description.
- [x] Cho phép không truyền description.
- [x] Cho phép truyền `null`.
- [x] Chuyển description rỗng sau trim thành `null`.
- [x] Reject description dài hơn 5000 ký tự.
- [x] Không expose `url_images` như input do client tự nhập.

Kết quả mong muốn:
  Metadata được normalize giống nhau ở create và update.

### 6. Schema multipart update

- [x] Chốt cách FastAPI nhận các field optional từ multipart.
- [x] `code` optional khi update.
- [x] `description` optional khi update.
- [x] Phân biệt không truyền description với chủ động clear description.
- [x] `remove_image_file_names` nhận được nhiều giá trị.
- [x] Trim và deduplicate `remove_image_file_names`.
- [x] Reject filename rỗng.
- [x] Không cho `remove_image_file_names` chứa path separator.
- [x] Không cho client truyền trực tiếp `url_images`.

Kết quả mong muốn:
  Update contract biểu diễn được cả sửa metadata, thêm ảnh và xóa ảnh.

### 7. Error contract

- [x] Bổ sung `IMAGE_ASSET_NOT_FOUND`.
- [x] Bổ sung `IMAGE_ASSET_CODE_EXISTS`.
- [x] Bổ sung `IMAGE_ASSET_INVALID_ID`.
- [x] Bổ sung `IMAGE_ASSET_EMPTY_UPDATE`.
- [x] Bổ sung `IMAGE_ASSET_FILE_REQUIRED`.
- [x] Bổ sung `IMAGE_ASSET_IMAGE_NOT_FOUND`.
- [x] Bổ sung error validation storage nếu dùng error code tập trung.
- [x] Chốt mapping duplicate index thành `409 Conflict`.

Kết quả mong muốn:
  API phase sau có error code ổn định, không trả exception nội bộ.

### 8. Test Phase 2

- [x] Test model chấp nhận description `None`.
- [x] Test description tối đa 5000 ký tự.
- [x] Test description vượt 5000 ký tự bị reject.
- [x] Test description rỗng được normalize thành `None`.
- [x] Test code được trim và uppercase.
- [x] Test code rỗng bị reject.
- [x] Test response serialize đủ field.
- [x] Test list schema.
- [x] Test `url_images` rỗng bị reject ở model.
- [x] Test update phân biệt field không gửi và field clear.
- [x] Test normalize/deduplicate `remove_image_file_names`.
- [ ] Test permission name được tạo đúng trên database.

Kết quả mong muốn:
  Model và schema ổn định trước khi nối filesystem.

## Acceptance criteria

- [x] Collection `image_assets` được đăng ký.
- [x] `code` có unique index.
- [x] `description` nullable và tối đa 5000 ký tự.
- [x] `url_images` không thể rỗng.
- [x] Client không thể tự set URL ảnh.
- [ ] Permission CRUD được tạo đúng trên database.
- [x] Test Phase 2 pass.

## Ghi chú mở

- Nếu cần giữ description là chuỗi rỗng thay vì `null`, phải đổi contract trước khi implement; tài liệu hiện chốt rỗng thành `null`.
- Khi test unique index bằng mock model, vẫn cần một integration check với MongoDB ở môi trường triển khai.
- Nếu database đã có dữ liệu trước khi tạo unique index, cần thống kê code trùng sau khi trim/uppercase, hợp nhất hoặc xóa record trùng, rồi mới cho startup tạo index.
