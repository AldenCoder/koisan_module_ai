# Task List Phase 3: Upload ảnh và gửi Pancake message

## Mục tiêu

Phase 3 hoàn thiện đường gửi media qua Pancake: reuse `content_id` đã cache nếu có, upload file local lên endpoint `upload_contents` khi cần, lấy `content_id`, lưu `content_id` vào cache, xóa file local sau upload thành công khi reuse bật, gom `content_ids`, gửi text trước và gửi image message sau.

Kết quả mong muốn:

- BE upload được file local lên Pancake.
- BE bỏ qua upload nếu cache đã có `content_id` và `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true`.
- BE parse được `content_id` từ response upload.
- BE xóa file local sau upload thành công nếu `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true`.
- BE gửi text message trước.
- BE gửi image message sau bằng `content_ids`.
- BE không gửi image message nếu không có `content_ids` hợp lệ.

## Đầu vào đã chốt

- Input của phase là object reply đã có text sạch và danh sách ảnh từ Phase 2; ảnh có thể chỉ có `content_id` cache mà không còn file local nếu reuse bật.
- Endpoint upload là `POST /api/public_api/v1/pages/{page_id}/upload_contents`.
- Endpoint gửi message là `POST /api/public_api/v1/pages/{page_id}/conversations/{conversation_id}/messages`.
- Action inbox là `reply_inbox`.
- Token Pancake lấy từ cấu hình hiện tại, không hard-code và không log.
- `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true` cho phép gửi ảnh bằng `content_id` đã lưu trong cache.

## Ngoài phạm vi Phase 3

- Không download ảnh.
- Không parse Drive link.
- Không thay đổi rule duplicate/pause/admin takeover.
- Không thêm queue retry persistent nếu chưa có yêu cầu riêng.

## File chính dự kiến sửa

- [app/services/pancake_message_service.py](../../app/services/pancake_message_service.py)
- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- `app/services/pancake_drive_image_service.py`
- `tests/test_pancake_message_service.py`
- `tests/test_pancake_webhook.py`

## Checklist

### 1. Upload file local lên Pancake

- [x] Thêm helper/service upload file local lên `upload_contents`.
- [x] Service nhận `page_id` và local file path.
- [x] Gửi request dạng `multipart/form-data`.
- [x] Field form data dùng `file=@storage/pancake_images/{drive_file_id}.jpg`.
- [x] Dùng base URL Pancake hiện tại.
- [x] Dùng token từ settings/config.
- [x] Set timeout `PANCAKE_IMAGE_UPLOAD_TIMEOUT_SECONDS`.
- [x] Không log token, auth header hoặc URL chứa token.

Kết quả mong muốn:
  Upload media được đóng gói trong service riêng, test được bằng mock HTTP.

### 2. Parse response upload

- [x] Parse `content_id` từ response thành công.
- [x] Nếu Pancake bọc `content_id` trong field khác, normalize về object nội bộ.
- [x] Trả object có `ok`, `content_id`, `status_code`, `reason`, `response_data` rút gọn nếu cần.
- [x] Nếu thiếu `content_id`, coi là upload failed.
- [x] Phân loại lỗi auth/permission/payload sai là non-retryable nếu có retry.
- [x] Phân loại timeout/5xx là retryable nếu có retry giới hạn.

Kết quả mong muốn:
  Webhook flow không phụ thuộc vào shape raw response của Pancake.

### 3. Update cache sau upload

- [x] Lưu `content_id` vào entry theo `drive_file_id`.
- [x] Lưu `uploaded_at`.
- [x] Giữ lại metadata download đã có.
- [x] Đọc lại `content_id` đã lưu trong cache khi chuẩn bị danh sách ảnh gửi Pancake.
- [x] Ghi cache bằng atomic write hoặc lock.
- [x] Xóa file local sau khi upload thành công nếu `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true`.
- [x] Nếu upload lỗi, lưu lỗi vào result/log nhưng không ghi `content_id` rỗng.

Kết quả mong muốn:
  Cache phản ánh file nào đã upload thành công và `content_id` tương ứng.

### 4. Gửi text message trước

- [x] Nếu text hợp lệ, gọi service gửi Pancake text reply hiện tại.
- [x] Body có `action = "reply_inbox"` và `message`.
- [x] Dùng `page_id` và `pancake_conversation_id`.
- [x] Nếu text rỗng, không gửi text message rỗng.
- [x] Log response rút gọn.

Kết quả mong muốn:
  Khách nhận được câu trả lời text trước khi ảnh được gửi.

### 5. Gửi image message sau

- [x] Nếu `PANCAKE_REUSE_UPLOADED_CONTENT_ID=true` và ảnh đã có `content_id`, gom `content_id` đó và bỏ qua upload.
- [x] Nếu reuse bật và ảnh đã có `content_id`, không yêu cầu file local còn tồn tại.
- [x] Nếu `PANCAKE_REUSE_UPLOADED_CONTENT_ID=false`, upload lại file local và cập nhật `content_id` mới.
- [x] Gom các `content_id` upload thành công.
- [x] Không gửi image message nếu danh sách `content_ids` rỗng.
- [x] Body có `action = "reply_inbox"` và `content_ids`.
- [x] Dùng cùng `page_id` và `pancake_conversation_id`.
- [x] Parse response Pancake thành object kết quả nội bộ.
- [x] Log success/failure rút gọn, không log token.

Kết quả mong muốn:
  Ảnh được gửi vào hội thoại Pancake ở tin nhắn thứ hai.

### 6. Test phase 3

- [x] Test upload multipart dùng đúng endpoint `upload_contents`.
- [x] Test upload gửi đúng field `file`.
- [x] Test parse `content_id` thành công.
- [x] Test upload response thiếu `content_id` trả reason rõ ràng.
- [x] Test lưu `content_id` vào cache sau upload thành công.
- [x] Test xóa file local sau upload thành công khi reuse bật.
- [x] Test reuse `content_id` cache thì không gọi upload.
- [x] Test tắt reuse thì vẫn upload file local và dùng `content_id` mới.
- [x] Test gửi text message trước image message.
- [x] Test gửi image message với body có `content_ids`.
- [x] Test không gửi image message khi `content_ids` rỗng.
- [x] Test token không xuất hiện trong log/response test được.

Kết quả mong muốn:
  Upload và gửi message được cover bằng mock, không gọi Pancake thật.

## Acceptance criteria

- [x] BE upload được file local lên Pancake.
- [x] BE lấy được `content_id`.
- [x] BE lưu được `content_id` vào cache.
- [x] BE xóa được file local sau upload thành công khi reuse bật.
- [x] BE reuse được `content_id` đã cache khi cấu hình bật.
- [x] BE gửi text trước.
- [x] BE gửi ảnh sau bằng `content_ids`.
- [x] Test phase này pass.

## Ghi chú mở

- Nếu phát hiện `content_id` Pancake không tái sử dụng lâu dài, đặt `PANCAKE_REUSE_UPLOADED_CONTENT_ID=false` để backend upload lại từ file local nếu còn, hoặc download lại từ Drive rồi upload.
- Nếu Pancake giới hạn số `content_ids` mỗi message, cần enforce limit trước khi gửi.
