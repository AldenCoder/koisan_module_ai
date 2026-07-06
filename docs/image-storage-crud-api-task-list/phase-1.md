# Task List Phase 1: Storage, cấu hình và public URL

## Mục tiêu

Phase 1 chuẩn bị nền tảng lưu file ảnh trong `storage/rag_images` và public ảnh qua một static route riêng. Phase này chốt toàn bộ config, quy tắc đường dẫn và tên file để các phase sau không hard-code rải rác.

Kết quả mong muốn:

- Backend có config thống nhất cho thư mục lưu ảnh và URL public.
- Thư mục `storage/rag_images` luôn tồn tại trước khi mount hoặc ghi file.
- Ảnh trong storage có thể truy cập qua URL `/rag-images/{file_name}`.
- Tên file có dạng `{CODE}_{random_id}.jpg`.
- Không có đường dẫn nào thoát ra ngoài `storage/rag_images`.
- File runtime không bị commit vào Git.

## Đầu vào đã chốt

- Thư mục lưu file là `storage/rag_images`.
- Public path mặc định là `/rag-images`.
- Tên file luôn có đuôi `.jpg`.
- Prefix tên file lấy từ `code` đã chuẩn hóa.
- ID ngẫu nhiên phải đủ dài và được tạo phía server.
- Target tối ưu ưu tiên 500.000 bytes được fix cứng trong code.
- `RAG_IMAGE_TARGET_MAX_BYTES` là giới hạn fallback cuối cùng, mặc định `1000000`.
- `Pillow` và `python-multipart` đã có trong `requirements.txt`.

## Ngoài phạm vi Phase 1

- Chưa tạo model MongoDB.
- Chưa nhận multipart upload.
- Chưa resize hoặc nén ảnh.
- Chưa tạo CRUD router.
- Chưa ghi hoặc xóa file ảnh thật từ request API.

## File chính dự kiến sửa

- [app/core/config.py](../../app/core/config.py)
- [app/main.py](../../app/main.py)
- [.env.example](../../.env.example)
- [.gitignore](../../.gitignore)
- `app/services/image_asset_service.py`, nếu đặt helper storage chung tại service này.
- `tests/test_image_asset_storage.py`, nếu tách test helper storage riêng.

## Checklist

> Trạng thái: Hoàn thành implementation và unit test ngày 12/06/2026.

### 1. Bổ sung config

- [x] Thêm `RAG_IMAGE_STORAGE_DIR`, mặc định `storage/rag_images`.
- [x] Thêm `RAG_IMAGE_PUBLIC_PATH`, mặc định `/rag-images`.
- [x] Thêm `RAG_IMAGE_TARGET_MAX_BYTES`, mặc định `1000000`.
- [x] Base URL public của ảnh dùng `BASE_URL`, không dùng config riêng.
- [x] Fix cứng width/height/JPEG quality trong code.
- [x] Không dùng config giới hạn số ảnh hoặc dung lượng upload gốc.
- [x] Ghi đầy đủ config mới vào `.env.example`.
- [x] Không thêm config riêng cho target ưu tiên 500.000 bytes.

Kết quả mong muốn:
  Mọi tham số triển khai có một nguồn cấu hình rõ ràng; target 500 KB vẫn là constant trong code.

### 2. Chuẩn bị storage directory

- [x] Resolve `RAG_IMAGE_STORAGE_DIR` thành absolute path trước khi sử dụng.
- [x] Tạo thư mục bằng cơ chế idempotent nếu chưa tồn tại.
- [x] Tạo thư mục trước khi khởi tạo `StaticFiles`.
- [x] Startup không lỗi nếu thư mục đã tồn tại.
- [x] Startup trả lỗi rõ nếu process không có quyền tạo hoặc ghi thư mục.
- [x] Không tự xóa nội dung storage khi ứng dụng restart.
- [x] Xác nhận `storage/` đã được ignore trong `.gitignore`.

Kết quả mong muốn:
  Backend khởi động ổn định và có storage writable trước khi nhận request.

### 3. Mount public static route

- [x] Mount `RAG_IMAGE_PUBLIC_PATH` vào `RAG_IMAGE_STORAGE_DIR`.
- [x] Không dùng chung route `/static` hiện có của `app/static`.
- [x] Chuẩn hóa public path có đúng một dấu `/` ở đầu và không có dấu `/` dư ở cuối.
- [x] Không bật directory listing.
- [x] File tồn tại trả đúng nội dung ảnh.
- [x] File không tồn tại trả `404`.
- [x] Static route chỉ đọc file, không cho upload hoặc delete trực tiếp.

Kết quả mong muốn:
  URL public ảnh hoạt động độc lập với static assets hiện có.

### 4. Chuẩn hóa code dùng trong tên file

- [x] Trim code.
- [x] Chuyển code thành chữ hoa.
- [x] Chỉ giữ các ký tự an toàn cho tên file.
- [x] Thay nhóm ký tự không an toàn bằng một dấu gạch dưới.
- [x] Loại dấu gạch dưới thừa ở đầu và cuối.
- [x] Không cho kết quả prefix rỗng.
- [x] Giới hạn độ dài prefix để tổng tên file không vượt giới hạn filesystem.
- [x] Không dùng raw code để nối trực tiếp vào path.

Kết quả mong muốn:
  Mọi code hợp lệ đều tạo được prefix filename an toàn và ổn định.

### 5. Sinh tên file duy nhất

- [x] Sinh tên theo dạng `{CODE}_{random_id}.jpg`.
- [x] Random ID chỉ dùng ký tự an toàn.
- [x] Random ID đủ dài để xác suất trùng rất thấp.
- [x] Không dùng tên file gốc từ client.
- [x] Kiểm tra collision với file hiện có trước khi ghi.
- [x] Nếu collision, sinh ID khác thay vì overwrite.
- [x] Có helper tách lại `code prefix`, `random_id` và extension khi cần rename do đổi code.

Kết quả mong muốn:
  Hai ảnh của cùng code luôn có tên khác nhau và không ghi đè file cũ.

### 6. Build public URL

- [x] Build URL từ base URL, public path và tên file đã lưu.
- [x] Loại dấu `/` dư khi ghép URL.
- [x] Không build URL từ local absolute path.
- [x] Không để lộ cấu trúc thư mục server trong URL.
- [x] URL lưu database luôn dùng public filename đã sanitize.
- [x] Chốt behavior khi thiếu base URL ở local/test.
- [x] Không lấy host tùy ý từ header request nếu chưa có cơ chế trusted proxy.

Kết quả mong muốn:
  URL lưu vào MongoDB ổn định, không phụ thuộc đường dẫn vật lý của server.

### 7. Bảo vệ path

- [x] Khi nhận filename để xóa, chỉ nhận basename.
- [x] Reject absolute path.
- [x] Reject filename có path separator.
- [x] Resolve candidate path và xác nhận vẫn nằm trong storage root.
- [x] Không follow path từ database nếu path đó không map về public route hợp lệ.
- [x] Không cho symlink dẫn ra ngoài storage nếu môi trường có thể tạo symlink.

Kết quả mong muốn:
  Không có thao tác đọc, rename hoặc xóa file ngoài `storage/rag_images`.

### 8. Test Phase 1

- [x] Test tạo storage directory khi chưa tồn tại.
- [x] Test không lỗi khi directory đã tồn tại.
- [x] Test normalize public path.
- [x] Test build public URL.
- [x] Test normalize code cho filename.
- [x] Test code có ký tự đặc biệt.
- [x] Test filename đúng dạng `{CODE}_{random_id}.jpg`.
- [x] Test hai lần sinh tên không trùng.
- [x] Test collision tạo lại ID.
- [x] Test reject path traversal.
- [x] Test file static tồn tại đọc được.
- [x] Test file static không tồn tại trả `404`.

Kết quả mong muốn:
  Storage helper và public route được cover trước khi nối vào CRUD.

## Acceptance criteria

- [x] Config storage/public URL được khai báo đầy đủ.
- [x] `storage/rag_images` được tạo an toàn.
- [x] `/rag-images/{file_name}` phục vụ được file ảnh.
- [x] Filename đúng dạng `{CODE}_{random_id}.jpg`.
- [x] Không thể resolve path ra ngoài storage root.
- [x] Storage runtime không được commit.
- [x] Test Phase 1 pass.

## Ghi chú mở

- Local filesystem chỉ phù hợp khi deployment có persistent volume.
- Nếu chạy nhiều instance không dùng chung volume, phase sau cần chuyển sang object storage thay vì tiếp tục mở rộng local storage.
