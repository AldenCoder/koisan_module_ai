# Task List Phase 1: Tách Drive link và chuẩn bị reply

## Mục tiêu

Phase 1 chuẩn hóa response AI trong flow Pancake: tách Drive file/folder link khỏi text, extract `drive_file_id` hoặc `drive_folder_id`, lookup folder link thành danh sách ảnh, và tạo object nội bộ ổn định để các phase sau cache/download/upload ảnh và gửi Pancake message.

Kết quả mong muốn:

- BE có helper tách Drive file/folder link từ AI text.
- BE có helper extract `drive_file_id` từ các dạng URL đã chốt.
- BE có helper extract `drive_folder_id` và lookup ảnh trực tiếp trong folder.
- BE tạo được object nội bộ gồm `text`, `drive_file_urls`, `drive_file_ids`, `drive_folder_urls`, `drive_folder_results`, `image_limit`, `content_ids` và `errors`.
- Nếu AI response không có Drive link, flow Pancake text reply hiện tại không đổi.

## Đầu vào đã chốt

- AI có thể trả text thuần kèm Drive file link hoặc Drive folder link.
- Drive file/folder link có thể nằm cùng dòng hoặc nhiều dòng trong reply text.
- BE chỉ tách raw Drive link khỏi bot reply text.
- User message đã lưu không bị rewrite.
- Giới hạn ảnh mặc định là 3.

## Ngoài phạm vi Phase 1

- Không download ảnh.
- Không ghi cache JSON.
- Không upload ảnh lên Pancake.
- Không gửi message có `content_ids`.
- Không thay đổi logic pause/duplicate/admin takeover.

## File chính dự kiến sửa

- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- `app/services/pancake_drive_image_service.py`, nếu tách helper riêng.
- `tests/test_pancake_webhook.py`
- `tests/test_pancake_drive_image_service.py`, nếu tách service riêng.

## Checklist

### 1. Tách Drive file link khỏi text

- [x] Detect Drive file link trong AI response text.
- [x] Detect Drive folder link trong AI response text.
- [x] Tách link dạng `https://drive.google.com/file/d/{drive_file_id}/view?usp=drive_link`.
- [x] Tách link dạng `https://drive.google.com/file/d/{drive_file_id}/view`.
- [x] Tách link dạng `https://drive.google.com/uc?export=download&id={drive_file_id}`.
- [x] Tách link dạng `https://drive.google.com/open?id={drive_file_id}`.
- [x] Tách link dạng `https://drive.google.com/drive/folders/{drive_folder_id}`.
- [x] Loại raw Drive link khỏi text gửi cho khách.
- [x] Trim khoảng trắng/dòng trống sau khi tách link.
- [x] Giữ thứ tự link theo thứ tự xuất hiện trong AI response.

Kết quả mong muốn:
  BE có text sạch để gửi Pancake, danh sách Drive file URL và danh sách Drive folder URL riêng để xử lý ảnh.

### 2. Extract `drive_file_id`

- [x] Extract id từ segment sau `/file/d/`.
- [x] Extract id từ query param `id`.
- [x] Bỏ qua URL không thuộc host `drive.google.com`.
- [x] Bỏ qua URL thiếu id hoặc id rỗng.
- [x] Loại duplicate `drive_file_id` trong cùng reply nếu cần.
- [x] Ghi lỗi cấp link vào `errors`, không raise làm hỏng toàn bộ reply.

Kết quả mong muốn:
  BE có danh sách `drive_file_ids` hợp lệ để phase cache/download xử lý tiếp.

### 2b. Extract `drive_folder_id` và lookup ảnh

- [x] Extract id từ segment sau `/drive/folders/`.
- [x] Gọi Google Drive folder lookup khi có `drive_folder_urls`.
- [x] Chỉ lấy file có MIME `image/jpeg` hoặc `image/png`.
- [x] Không crawl folder con.
- [x] Dedupe ảnh theo `drive_file_id`.
- [x] Giới hạn tổng số ảnh theo `image_limit`, mặc định 3.
- [x] Nếu folder lookup lỗi, ghi vào `errors` nhưng không làm hỏng text reply.

Kết quả mong muốn:
  Drive folder link được chuyển thành danh sách `drive_file_ids` để dùng chung phase cache/download/upload.

### 3. Tạo object nội bộ

- [x] Tạo object có field `text`.
- [x] Tạo object có field `drive_file_urls`.
- [x] Tạo object có field `drive_file_ids`.
- [x] Tạo object có field `drive_folder_urls`.
- [x] Tạo object có field `drive_folder_results`.
- [x] Tạo object có field `drive_folder_error_count`.
- [x] Tạo object có field `image_limit`, mặc định 3.
- [x] Tạo object có field `content_ids`, ban đầu rỗng.
- [x] Tạo object có field `errors`, ban đầu rỗng hoặc chứa lỗi parse.
- [x] Đảm bảo object dễ serialize/log ở mức rút gọn.

Kết quả mong muốn:
  Các phase sau không cần parse lại raw AI response.

### 4. Giữ nguyên flow khi không có Drive link

- [x] Nếu AI response không có Drive link, trả text như flow hiện tại.
- [x] Không gọi service cache/download/upload khi `drive_file_urls` rỗng.
- [x] Vẫn gọi folder lookup nếu `drive_file_urls` rỗng nhưng `drive_folder_urls` có dữ liệu.
- [x] Không thay đổi nội dung text nếu không có link cần tách.
- [x] Không thay đổi logic quota fallback đã có.

Kết quả mong muốn:
  Flow hiện tại không bị regression khi AI chỉ trả text.

### 5. Test phase 1

- [x] Test tách Drive link khỏi text nhiều dòng.
- [x] Test tách Drive folder link khỏi text nhiều dòng.
- [x] Test extract id từ `/file/d/{id}/view`.
- [x] Test extract id từ `uc?export=download&id={id}`.
- [x] Test extract id từ `open?id={id}`.
- [x] Test URL không phải Drive bị bỏ qua.
- [x] Test URL Drive sai format không crash.
- [x] Test Drive folder link được lookup thành danh sách `drive_file_ids`.
- [x] Test text sau khi tách link không còn raw Drive link.
- [x] Test không có Drive link thì output giữ text như cũ.

Kết quả mong muốn:
  Parser/prepare reply được cover bằng unit test, không cần gọi external service.

## Acceptance criteria

- [x] BE tách được Drive file link khỏi AI text.
- [x] BE tách được Drive folder link khỏi AI text.
- [x] BE extract được `drive_file_id`.
- [x] BE extract được `drive_folder_id` và lookup ảnh trong folder.
- [x] BE tạo được object nội bộ ổn định.
- [x] Flow text-only hiện tại không đổi khi AI không trả Drive link.
- [x] Test phase này pass.

## Ghi chú mở

- Nếu AI sau này trả structured field riêng cho `drive_file_urls`, helper nên merge với link trong text và dedupe.
- Nếu text chỉ còn rỗng sau khi tách link, phase gửi message sẽ quyết định có gửi ảnh không kèm text hay không.
