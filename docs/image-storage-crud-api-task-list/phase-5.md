# Task List Phase 5: Test, rollout và vận hành

## Mục tiêu

Phase 5 kiểm tra toàn bộ flow từ upload đến public URL, MongoDB và cleanup file. Test phải chạy local bằng `pytest -q`, không gọi external service và không phụ thuộc file thật bên ngoài workspace test.

Kết quả mong muốn:

- Storage helper được cover.
- Pipeline tối ưu ảnh được cover.
- CRUD service và router được cover.
- Rollback giữa database và filesystem được cover.
- Static URL được kiểm tra.
- Full test suite pass.
- Có checklist deploy persistent storage và base URL.

## Đầu vào đã chốt

- Repo dùng Python 3.11 theo `AGENTS.md`.
- Chạy test bằng `pytest -q`.
- Không chạy `pre-commit`.
- Dùng `tmp_path` cho storage test.
- Mock database hoặc Beanie query theo pattern test hiện tại.
- Không gọi URL internet.
- Pillow đã có trong dependency.

## Ngoài phạm vi Phase 5

- Không load test dung lượng lớn.
- Không penetration test đầy đủ.
- Không test S3/MinIO.
- Không test nhiều instance dùng chung volume.
- Không xây dashboard theo dõi storage.

## File test dự kiến sửa/thêm

- `tests/test_image_asset_storage.py`
- `tests/test_image_asset_model.py`
- `tests/test_image_asset_schema.py`
- `tests/test_image_asset_image_processing.py`
- `tests/test_image_asset_service.py`
- `tests/test_image_assets.py`
- [tests/README.md](../../tests/README.md), nếu cần ghi chú test mới.

## Checklist

> Trạng thái: Hoàn thành toàn bộ test local ngày 12/06/2026. Các mục rollout và vận hành cần môi trường staging/production vẫn đang chờ thực hiện.

### 1. Fixture ảnh test

- [x] Tạo ảnh JPEG bằng Pillow trong memory.
- [x] Tạo ảnh PNG có alpha.
- [x] Tạo ảnh WebP.
- [x] Tạo ảnh có EXIF orientation.
- [x] Tạo ảnh kích thước lớn để kích hoạt resize.
- [x] Tạo binary giả ảnh.
- [x] Không commit file ảnh dung lượng lớn nếu có thể generate trong test.
- [x] Fixture cho phép kiểm soát dimensions và dung lượng tương đối.

Kết quả mong muốn:
  Test reproducible, nhỏ và không phụ thuộc file ngoài repo.

### 2. Test config và storage

- [x] Test default `RAG_IMAGE_STORAGE_DIR`.
- [x] Test default `RAG_IMAGE_PUBLIC_PATH`.
- [x] Test default `RAG_IMAGE_TARGET_MAX_BYTES=1000000`.
- [x] Test tạo storage directory.
- [x] Test normalize public path.
- [x] Test build public URL.
- [x] Test filename sanitize.
- [x] Test filename random không trùng.
- [x] Test path traversal bị reject.
- [x] Test collision không overwrite.

Kết quả mong muốn:
  Nền tảng filesystem không phụ thuộc môi trường máy chạy test.

### 3. Test model và schema

- [x] Test code uppercase.
- [x] Test code rỗng bị reject.
- [x] Test duplicate code được map thành `409`.
- [x] Test description không truyền.
- [x] Test description `null`.
- [x] Test description rỗng thành `null`.
- [x] Test description đúng 5000 ký tự.
- [x] Test description trên 5000 ký tự bị reject.
- [x] Test `url_images` không rỗng.
- [x] Test response serialize đủ field.

Kết quả mong muốn:
  Contract dữ liệu đúng với tài liệu chính.

### 4. Test validate upload

- [x] Test JPEG hợp lệ.
- [x] Test PNG hợp lệ.
- [x] Test WebP hợp lệ.
- [x] Test file rỗng.
- [x] Test file giả content type.
- [x] Test ảnh corrupt.
- [x] Test format không hỗ trợ.
- [x] Test không còn giới hạn upload gốc ở app config.
- [x] Test tất cả `UploadFile` được đóng.

Kết quả mong muốn:
  Input không hợp lệ bị chặn trước khi tạo record.

### 5. Test tối ưu ảnh

- [x] Test EXIF orientation được áp dụng.
- [x] Test ảnh transparency có nền trắng.
- [x] Test output là JPEG.
- [x] Test output giữ tỷ lệ.
- [x] Test không upscale ảnh nhỏ.
- [x] Test ảnh có thể đạt target được tối ưu dưới 500.000 bytes.
- [x] Test pipeline dừng khi đã đạt target.
- [x] Test fallback chọn candidate chất lượng tốt nhất dưới `RAG_IMAGE_TARGET_MAX_BYTES`.
- [x] Test output fallback có thể lớn hơn 500.000 bytes nhưng không vượt hard limit.
- [x] Test reject khi không có candidate dưới hard limit.
- [x] Test metadata trả đúng original/stored size và dimensions.

Kết quả mong muốn:
  Rule 500 KB ưu tiên và 1 MB fallback được cover rõ ràng.

### 6. Test create service/API

- [x] Test create với một ảnh.
- [x] Test create với nhiều ảnh.
- [x] Test description không truyền.
- [x] Test filename chứa code.
- [x] Test URL database trỏ đúng public route.
- [x] Test thứ tự `url_images` theo thứ tự upload.
- [x] Test code đã tồn tại trả `409`.
- [x] Test race duplicate index trả `409`.
- [x] Test database insert lỗi rollback toàn bộ file mới.
- [x] Test một ảnh trong batch lỗi rollback các ảnh đã ghi.
- [x] Test permission create.
- [x] Test response `201`.

Kết quả mong muốn:
  Create không để lại file rác và trả đúng contract.

### 7. Test list/detail/by-code

- [x] Test list mặc định.
- [x] Test pagination.
- [x] Test size vượt giới hạn.
- [x] Test filter chính xác theo code.
- [x] Test keyword theo code.
- [x] Test keyword theo description.
- [x] Test keyword được escape regex.
- [x] Test sort updated mới nhất trước.
- [x] Test detail ID hợp lệ.
- [x] Test detail ID sai format trả `400`.
- [x] Test detail not found trả `404`.
- [x] Test lookup by code normalize chữ hoa.
- [x] Test lookup by code not found.
- [x] Test permission view.

Kết quả mong muốn:
  Toàn bộ read API hoạt động và không có regex injection.

### 8. Test update metadata

- [x] Test chỉ đổi description.
- [x] Test clear description về `null`.
- [x] Test chỉ đổi code.
- [x] Test đổi sang code trùng trả `409`.
- [x] Test body không thay đổi trả `400`.
- [x] Test update `updated_at`.
- [x] Test permission edit.

Kết quả mong muốn:
  Metadata update không ảnh hưởng ảnh khi không có yêu cầu thay đổi file.

### 9. Test update đổi code

- [x] Test rename toàn bộ file được giữ lại.
- [x] Test filename mới có prefix code mới.
- [x] Test random ID được giữ nguyên.
- [x] Test URL database được cập nhật.
- [x] Test rename một file lỗi rollback các file đã rename.
- [x] Test save database lỗi rollback filename về code cũ.
- [x] Test rollback lỗi có log.
- [x] Test file bị remove trong cùng request không cần rename.

Kết quả mong muốn:
  Đổi code không tạo URL chết hoặc file mang prefix cũ.

### 10. Test update thêm và xóa ảnh

- [x] Test upload thêm một ảnh.
- [x] Test upload thêm nhiều ảnh.
- [x] Test ảnh cũ vẫn giữ nguyên.
- [x] Test xóa một ảnh bằng `remove_image_file_names`.
- [x] Test xóa nhiều ảnh.
- [x] Test deduplicate filename cần xóa.
- [x] Test filename không thuộc record bị reject.
- [x] Test absolute path/path traversal bị reject.
- [x] Test vừa thêm ảnh mới vừa xóa ảnh cũ.
- [x] Test kết quả cuối giữ đúng thứ tự đã chốt.
- [x] Test không cho kết quả cuối rỗng.
- [x] Test upload thêm nhiều ảnh không bị chặn bởi giới hạn tổng số ảnh.
- [x] Test database lỗi xóa file mới nhưng không xóa file cũ.
- [x] Test database success rồi mới xóa file cũ.
- [x] Test cleanup file cũ lỗi vẫn trả update thành công và có warning.

Kết quả mong muốn:
  Một PATCH xử lý chính xác toàn bộ thay đổi ảnh.

### 11. Test delete record

- [x] Test delete record thành công.
- [x] Test document bị xóa.
- [x] Test toàn bộ file được dọn.
- [x] Test file đã mất không làm delete lỗi.
- [x] Test cleanup một file lỗi vẫn hoàn thành delete và log warning.
- [x] Test ID sai format trả `400`.
- [x] Test record không tồn tại trả `404`.
- [x] Test delete lần hai trả `404`.
- [x] Test permission delete.
- [x] Test response `204`.

Kết quả mong muốn:
  Xóa nhóm ảnh đúng nghĩa là xóa record và cleanup toàn bộ ảnh liên quan.

### 12. Test static route

- [x] Test URL ảnh vừa tạo truy cập được.
- [x] Test response có content type ảnh phù hợp.
- [x] Test file không tồn tại trả `404`.
- [x] Test không browse directory.
- [x] Test route `/static` hiện có không bị ảnh hưởng.
- [x] Test public URL dùng đúng base URL cấu hình.

Kết quả mong muốn:
  URL lưu database thực sự có thể dùng để tải ảnh.

### 13. Chạy test tổng

- [x] Chạy test riêng cho image asset.
- [x] Chạy `pytest -q`.
- [x] Không chạy `pre-commit`.
- [x] Sửa expectation test cũ nếu router/config mới thay đổi contract hợp lệ.
- [x] Xác nhận test không ghi file vào `storage/rag_images` thật.
- [x] Xác nhận test cleanup toàn bộ `tmp_path`.

Kết quả mong muốn:
  Test suite pass và không làm bẩn workspace.

### 14. Rollout

- [ ] Gắn persistent volume vào `storage/rag_images`.
- [ ] Xác nhận process có quyền read/write volume.
- [ ] Xác nhận reverse proxy/infra có chính sách multipart phù hợp nếu cần giới hạn request lớn.
- [ ] Xác nhận route `/rag-images` được proxy/public.
- [ ] Deploy model và unique index.
- [ ] Kiểm tra permission admin/user sau startup.
- [ ] Upload thử một code trên staging.
- [ ] Mở URL ảnh từ bên ngoài server.
- [ ] Test update thêm/xóa ảnh trên staging.
- [ ] Test delete record và kiểm tra volume.

Kết quả mong muốn:
  Feature hoạt động thực tế sau reverse proxy và persistent volume.

### 15. Vận hành

- [ ] Theo dõi dung lượng volume.
- [ ] Theo dõi log optimize fallback trên 500 KB.
- [ ] Theo dõi file cleanup lỗi.
- [ ] Có cách kiểm tra orphan file định kỳ.
- [ ] Backup database cùng thư mục ảnh.
- [ ] Không scale nhiều instance nếu chưa có shared storage.
- [ ] Ghi chú phương án chuyển object storage khi cần scale.

Kết quả mong muốn:
  Team biết các giới hạn của local storage và có tín hiệu để xử lý sự cố.

## Acceptance criteria

- [x] Unit test storage pass.
- [x] Unit test image processing pass.
- [x] CRUD service/API test pass.
- [x] Rollback filesystem/database được cover.
- [x] Static URL được verify.
- [x] `pytest -q` pass.
- [ ] Staging có persistent volume và public base URL đúng.
- [ ] Upload, update và delete smoke test thành công.

## Ghi chú mở

- Test ảnh nên generate bằng Pillow để tránh tăng kích thước repo.
- Nếu môi trường CI không có MongoDB, tách test model/service bằng mock và giữ integration test database cho pipeline deploy.
