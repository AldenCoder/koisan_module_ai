# Task List Phase 3: Detect màu từ AI reply và chọn ảnh đúng màu

## Mục tiêu

Phase 3 thêm logic detect `requested_color` từ text reply của AI và dùng màu đó để chọn ảnh từ Drive folder. Logic này chỉ chạy khi AI reply có Drive link và text có cụm rõ ràng theo dạng `màu + tên màu`.

Kết quả mong muốn:

- Reply không có Drive link không chạy color filter.
- Reply có Drive link nhưng không có cụm `màu + tên màu` giữ random selection hiện tại.
- Reply có Drive link và có cụm `màu + tên màu` ưu tiên chọn ảnh match màu.
- Có màu nhưng không có ảnh match thì fallback random theo logic cũ.

## Đầu vào đã chốt

- Text AI đã được tách Drive link trước khi detect màu.
- Folder result đã có `drive_file_name` và `drive_file_color`.
- `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` vẫn là giới hạn mỗi folder.

## Ngoài phạm vi Phase 3

- Không hỗ trợ nhiều màu trong một reply.
- Không dùng computer vision để nhận diện màu.
- Không đổi Pancake upload/send API.

## File chính dự kiến sửa

- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [app/services/pancake_drive_image_service.py](../../app/services/pancake_drive_image_service.py)
- `app/services/pancake_drive_image_color_service.py`, nếu tách helper riêng.
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)

## Checklist

### 1. Detect màu từ text AI

- [x] Chỉ detect màu nếu AI reply có Drive link.
- [x] Normalize text về lowercase.
- [x] Normalize khoảng trắng.
- [x] Chỉ nhận trigger token `màu` hoặc `mau`.
- [x] Không bỏ dấu trước khi nhận diện trigger để tránh nhầm `mẫu đỏ`.
- [x] Sau khi xác định trigger, mới bỏ dấu khi so sánh tên màu phía sau.
- [x] Normalize alias màu bằng cùng rule.
- [x] Ưu tiên alias dài hơn trước.
- [x] Trả `requested_color=null` nếu không match.

Kết quả mong muốn:
  `màu xanh ngọc` detect thành `xanhngoc`, `màu đỏ` detect thành `do`; `váy đỏ` và `mẫu đỏ` không kích hoạt filter.

### 2. Chọn ảnh theo màu

- [x] Nếu không có `requested_color`, gọi random selection hiện tại.
- [x] Nếu có `requested_color`, lọc candidates theo `drive_file_color`.
- [x] Nếu ảnh match màu có cache item thiếu `drive_file_name` hoặc `drive_file_color`, yêu cầu phase cache xóa entry và chạy lại download/cache.
- [x] Nếu có nhiều ảnh match, random trong nhóm match.
- [x] Giới hạn ảnh match theo `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT` mỗi folder.
- [x] Nếu không có ảnh match, fallback random theo logic cũ.
- [x] Ghi reason `drive_color_no_match_random_fallback` khi fallback random vì không match màu.

Kết quả mong muốn:
  BE gửi đúng ảnh màu được AI nhắc khi có match; nếu chưa có filename màu đúng convention thì vẫn gửi random ảnh theo flow cũ.

### 3. Test phase 3

- [x] Test không Drive link thì không detect màu.
- [x] Test Drive link không màu thì giữ random selection.
- [x] Test Drive link có `màu đỏ` chỉ chọn ảnh `do`.
- [x] Test Drive link có `màu xanh ngọc` chỉ chọn ảnh `xanhngoc`.
- [x] Test Drive link có `váy đỏ` nhưng không có chữ `màu` thì giữ random selection.
- [x] Test Drive link có `mẫu đỏ` thì giữ random selection.
- [x] Test Drive link có `màu đỏ` và cache item thiếu metadata thì không reuse `content_id` cũ.
- [x] Test không có ảnh match thì fallback random theo logic cũ.
- [x] Test nhiều folder áp dụng cùng requested color cho từng folder.

## Acceptance criteria

- [x] Color filter chỉ chạy khi có Drive link.
- [x] Color filter chỉ detect màu từ pattern `màu + tên màu`.
- [x] Không có requested color thì flow cũ không đổi.
- [x] Có requested color thì ưu tiên chọn ảnh match màu.
- [x] Cache item thiếu metadata không được dùng để gửi ảnh theo requested color.
- [x] Không có match thì fallback random theo logic cũ.
- [x] Unit test phase này pass.

## Ghi chú mở

- Nếu AI trả structured color trong tương lai, helper có thể ưu tiên structured field rồi mới fallback detect từ text.
