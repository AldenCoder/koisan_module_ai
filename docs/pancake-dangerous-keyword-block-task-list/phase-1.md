# Task List Phase 1: Service đọc và match dangerous keyword

## Mục tiêu

Phase 1 tạo helper/service chịu trách nhiệm đọc [docs/dangerous_keywords.md](../dangerous_keywords.md), cache danh sách keyword theo `mtime`, và match text khách hàng theo rule literal có ranh giới từ. Service phải trả object nội bộ ổn định để Pancake webhook dùng được và test được độc lập.

Kết quả mong muốn:

- Keyword file được đọc một cách có kiểm soát.
- Keyword được trim/dedupe đúng rule.
- Cache tránh đọc file lại ở mọi request nếu file chưa đổi.
- Reload khi `mtime` thay đổi.
- Match literal có ranh giới từ, có phân biệt dấu và hoa/thường.
- Lỗi load keyword file khiến message khách hàng fail closed.

## Đầu vào đã chốt

- Source keyword là `docs/dangerous_keywords.md`.
- Không lowercase/casefold.
- Không bỏ dấu tiếng Việt.
- Không collapse khoảng trắng bên trong.
- Không tạo thêm keyword không dấu.
- Không thêm env bật/tắt.
- Không thêm env đổi path.

## Ngoài phạm vi Phase 1

- Chưa gắn service vào Pancake webhook.
- Chưa chỉnh raw payload logging.
- Chưa thêm audit storage.
- Chưa phân loại keyword theo category.
- Chưa tối ưu bằng trie/regex nâng cao.
- Chưa thay đổi file keyword.

## File chính dự kiến sửa

- `app/services/dangerous_keyword_service.py`
- `tests/test_dangerous_keyword_service.py`

## Checklist

### 1. Tạo service/helper

- [x] Tạo module `app/services/dangerous_keyword_service.py`.
- [x] Định nghĩa constant path trỏ tới `docs/dangerous_keywords.md`.
- [x] Định nghĩa reason `dangerous_keyword_matched`.
- [x] Định nghĩa reason lỗi load keyword nếu cần.
- [x] Trả object khi match gồm `blocked`, `reason`, `matched_keyword`.
- [x] Trả object khi không match gồm `blocked=False`, `reason=None`, `matched_keyword=None`.

Kết quả mong muốn:
  Webhook có một API nhỏ, ổn định để gọi block check.

### 2. Đọc và chuẩn hóa keyword

- [x] Đọc file keyword bằng encoding UTF-8.
- [x] Bỏ qua dòng rỗng.
- [x] Trim khoảng trắng đầu/cuối từng dòng.
- [x] Dedupe keyword theo giá trị sau trim.
- [x] Giữ thứ tự keyword sau dedupe.
- [x] Không lowercase/casefold keyword.
- [x] Không bỏ dấu keyword.
- [x] Không collapse khoảng trắng bên trong keyword.
- [x] Không parse markdown heading/bảng/format đặc biệt.

Kết quả mong muốn:
  Keyword được dùng đúng như nội dung file, không phát sinh rule ẩn.

### 3. Cache và reload theo `mtime`

- [x] Cache danh sách keyword trong process.
- [x] Cache `mtime` của file keyword.
- [x] Không đọc lại file nếu `mtime` chưa đổi.
- [x] Reload khi `mtime` thay đổi.
- [x] Có cách reset cache trong test nếu cần.
- [x] Không dùng env để điều khiển reload.

Kết quả mong muốn:
  Runtime nhẹ hơn nhưng vẫn nhận thay đổi keyword file khi file đổi.

### 4. Match literal có ranh giới từ

- [x] Nhận input text dạng string.
- [x] Text `None` hoặc rỗng trả không block.
- [x] Kiểm tra keyword xuất hiện nguyên văn với ranh giới từ hợp lệ.
- [x] Match có phân biệt dấu tiếng Việt.
- [x] Match có phân biệt hoa/thường.
- [x] Match keyword kỹ thuật như `.env`, `../`, `os.system`.
- [x] Không match keyword ngắn bên trong từ/token khác, ví dụ `db` không match `feedback`.
- [x] Dừng ở keyword đầu tiên match theo thứ tự file.
- [x] Không trả full text trong result.

Kết quả mong muốn:
  Match behavior đúng tài liệu và dễ dự đoán.

### 5. Fail closed khi không load được keyword

- [x] Nếu file không tồn tại, service trả hoặc raise lỗi rõ.
- [x] Nếu file không đọc được, service trả hoặc raise lỗi rõ.
- [x] Không gọi AI cho message khách hàng khi keyword file lỗi.
- [x] Không log raw keyword file nếu lỗi đọc.
- [x] Không log text khách hàng khi lỗi đọc trong path block.

Kết quả mong muốn:
  Khi lớp bảo vệ không hoạt động, backend không gửi text khách hàng sang AI.

## Acceptance criteria

- [x] Service đọc keyword từ `docs/dangerous_keywords.md`.
- [x] Service cache/reload theo `mtime`.
- [x] Service match literal có ranh giới từ đúng dấu và hoa/thường.
- [x] Service không trả full text khách hàng trong result.
- [x] Lỗi load keyword file có reason rõ để webhook fail closed.
- [x] Unit test service pass.

## Ghi chú mở

- Nếu danh sách keyword lớn lên đáng kể, có thể mở task tối ưu matcher sau.
- Nếu cần category/mức độ nguy hiểm, nên mở rộng contract result ở task riêng.
