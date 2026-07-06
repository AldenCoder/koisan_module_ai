# Task List Phase 2: Tích hợp response Brain vào pipeline BE

## Mục tiêu

Phase 2 nối luồng Brain với Drive image lookup trong BE. Sau khi BE nhận response/data từ Brain, BE sẽ tách text, tách Drive link, gọi service Google Drive, chọn 1-3 ảnh, và tạo kết quả nội bộ để phase gửi Facebook sử dụng.

Kết quả mong muốn:

- BE xử lý được response Brain dạng structured payload.
- BE fallback được với response text thuần có Drive link.
- BE làm sạch text trước khi gửi khách.
- BE chọn tối đa 1-3 ảnh sản phẩm.

## Đầu vào đã chốt

- Brain được cấu hình qua `FB_AI_CHAT_URL`.
- Brain có thể trả `text`.
- Brain có thể trả `drive_folder_urls`.
- Nếu Brain chưa trả structured field, BE parse Drive link từ text.
- `image_limit` nếu có không được vượt quá 3.

## Ngoài phạm vi Phase 2

- Chưa gửi Messenger API.
- Chưa xử lý fallback Facebook media send.
- Không thêm endpoint mới để Brain gọi lấy ảnh.
- Không implement logic catalog/intent bên trong Brain.

## File chính dự kiến sửa

- [app/api/v1/facebook_webhook.py](../../app/api/v1/facebook_webhook.py)
- [app/api/v1/response_message.py](../../app/api/v1/response_message.py)
- [app/services/ai_service.py](../../app/services/ai_service.py)
- [app/services/google_drive_image_service.py](../../app/services/google_drive_image_service.py)
- [tests/test_facebook_webhook_forward.py](../../tests/test_facebook_webhook_forward.py)

## Checklist

### 1. Chuẩn hóa response Brain

- [x] Xác định shape response hiện tại từ `FB_AI_CHAT_URL`.
- [x] Map response structured vào object nội bộ gồm `text`, `drive_folder_urls`, `image_limit`.
- [x] Hỗ trợ response chỉ là string/text.
- [x] Hỗ trợ response có nhiều Drive folder link.
- [x] Không làm hỏng luồng chat text hiện tại nếu không có Drive link.

Kết quả mong muốn:
  BE có một object nội bộ thống nhất bất kể Brain trả structured hay text thuần.

### 2. Tách và làm sạch text

- [x] Tách Drive folder URL khỏi text.
- [x] Tách image URL nếu Brain đã lỡ trả raw `lh3.googleusercontent.com/d/{id}`.
- [x] Xóa dòng trống dư sau khi bỏ URL.
- [x] Giữ nội dung text tự nhiên cho khách.
- [x] Nếu text rỗng nhưng có ảnh, quyết định dùng text mặc định hoặc gửi ảnh trực tiếp theo behavior hiện tại.

Kết quả mong muốn:
  Khách không nhận raw Drive link dài trong tin nhắn text.

### 3. Gọi Drive lookup từ pipeline BE

- [x] Nếu có Drive folder URL, gọi Google Drive image lookup service.
- [x] Nếu không có Drive folder URL, bỏ qua lookup và giữ luồng text hiện tại.
- [x] Folder lỗi không làm fail toàn bộ response.
- [x] Drive lookup lỗi vẫn cho phép gửi text nếu có.
- [x] Không expose Google Drive lookup thành contract bắt buộc cho Brain.

Kết quả mong muốn:
  BE tự lấy ảnh sau khi nhận data Brain.

### 4. Chọn 1-3 ảnh

- [x] Dùng `image_limit` nếu Brain trả, nhưng cap tối đa 3.
- [x] Mặc định lấy tối đa 3 ảnh.
- [x] Ưu tiên folder theo thứ tự Brain trả.
- [x] Loại duplicate image URL.
- [x] Không gửi ảnh nếu không có URL hợp lệ.

Kết quả mong muốn:
  Mỗi lượt trả lời chỉ gửi danh sách ảnh nhỏ, đúng phương án mới.

### 5. Test tích hợp Brain response

- [x] Test Brain trả text không có Drive link.
- [x] Test Brain trả structured `drive_folder_urls`.
- [x] Test Brain trả plain text có Drive link.
- [x] Test text sau khi clean không còn Drive link.
- [x] Test Drive lookup được gọi khi có link.
- [x] Test Drive lookup không được gọi khi không có link.
- [x] Test giới hạn 1-3 ảnh.

Kết quả mong muốn:
  Pipeline mới được kiểm chứng trước khi nối vào Messenger send.

## Acceptance criteria

- [x] BE nhận được data từ Brain và tạo object nội bộ thống nhất.
- [x] BE tự tách Drive link từ response Brain.
- [x] BE tự lấy ảnh Drive khi có link.
- [x] BE chọn tối đa 1-3 ảnh.
- [x] BE không còn phụ thuộc Brain gọi endpoint `/drive-images`.

## Ghi chú mở

- Nếu Brain có thể chỉnh sớm, nên ưu tiên structured `drive_folder_urls` để giảm rủi ro regex nhầm link.
- Endpoint `/drive-images` cũ đã được remove; webhook flow hiện gọi Drive lookup service trực tiếp.
