# Task List Phase 2: Bóc mã sản phẩm và tạo prompt lookbook

## Mục tiêu

Phase 2 chuẩn hóa description, bóc toàn bộ mã sản phẩm hợp lệ và tạo prompt cố định cho AI. Prompt phải yêu cầu AI tư vấn mẫu và gửi ảnh lookbook trong cùng một request.

Kết quả mong muốn:

- `product_codes` là danh sách mã hợp lệ, đã dedupe, giữ thứ tự xuất hiện.
- Không nhận nhầm `ad_id`, `post_id` hoặc chuỗi toàn số.
- Prompt một mã và nhiều mã đúng contract.
- Nếu không có mã, flow dừng an toàn trước AI.

## Đầu vào đã chốt

- Description đến từ source detail đã hydrate ở Phase 1.
- Không parse mã từ system text.
- Regex phase đầu: `\b[A-Z]{1,3}\d{5,10}\b`.
- Prompt format: `tư vấn mẫu {product_codes_csv} và gửi ảnh lookbook`.

## Ngoài phạm vi Phase 2

- Chưa gọi AI.
- Chưa gửi Pancake reply.
- Chưa xử lý format mã có khoảng trắng hoặc dấu gạch nếu business chưa xác nhận.

## File chính dự kiến sửa

- `app/services/pancake_auto_consult_service.py`, nếu tách helper riêng.
- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [app/core/config.py](../../app/core/config.py), nếu thêm regex config.
- `tests/test_pancake_auto_consult_service.py`, nếu tách helper riêng.
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)

## Checklist

### 1. Normalize description

- [x] Convert description về string an toàn.
- [x] Strip đầu/cuối.
- [x] Gom nhiều whitespace thành một khoảng trắng.
- [x] Giữ nguyên chữ hoa/thường đủ để regex uppercase hoạt động.
- [x] Không tự sửa hoặc suy luận mã nếu description thiếu mã.

Kết quả mong muốn:
  Parser chạy ổn với caption có newline, emoji, HTML text hoặc khoảng trắng lộn xộn.

### 2. Extract product codes

- [x] Dùng regex mặc định `\b[A-Z]{1,3}\d{5,10}\b`.
- [x] Tìm tất cả match trong description.
- [x] Bỏ qua chuỗi toàn số.
- [x] Dedupe mã trùng nhau.
- [x] Giữ thứ tự xuất hiện đầu tiên.
- [x] Return `product_codes=[]` khi không match.
- [x] Log `product_code_count`.
- [x] Không log raw full description nếu dài.

Kết quả mong muốn:
  `S7671263 và W2651713` tạo `["S7671263", "W2651713"]`.

### 3. Build prompt

- [x] Join codes bằng `, ` thành `product_codes_csv`.
- [x] Tạo prompt `tư vấn mẫu {product_codes_csv} và gửi ảnh lookbook`.
- [x] Một mã tạo `tư vấn mẫu S7671263 và gửi ảnh lookbook`.
- [x] Nhiều mã tạo `tư vấn mẫu S7671263, S7672889 và gửi ảnh lookbook`.
- [x] Nếu `product_codes` rỗng, return `pancake_product_code_missing`.

Kết quả mong muốn:
  BE gọi AI một lần cho tất cả mã trong caption, tránh spam khách.

## Acceptance criteria

- [x] Test parse một mã pass.
- [x] Test parse nhiều mã pass.
- [x] Test dedupe mã trùng pass.
- [x] Test không parse chuỗi toàn số pass.
- [x] Test prompt một mã pass.
- [x] Test prompt nhiều mã pass.
- [x] Test không có mã return `pancake_product_code_missing`.

## Ghi chú mở

- Nếu business muốn giới hạn số mã tối đa trong một prompt, nên thêm config và reason rõ ràng thay vì cắt âm thầm.
