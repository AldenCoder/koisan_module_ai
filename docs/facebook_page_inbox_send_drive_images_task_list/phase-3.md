# Task List Phase 3: Gửi text trước và ảnh sau qua Facebook Page Inbox

## Mục tiêu

Phase 3 dùng kết quả nội bộ từ Phase 2 để gửi phản hồi cho khách trên Facebook Page Inbox. BE gửi tin nhắn text trước, sau đó gửi ảnh ở message thứ hai qua Messenger Send API.

Kết quả mong muốn:

- Text không chứa raw Drive link hoặc raw image URL.
- Khách nhận text trước.
- Nếu có ảnh, khách nhận 1-3 ảnh sau.
- Payload gửi Facebook đúng schema hiện tại của Messenger Send API.

## Đầu vào đã chốt

Object nội bộ từ phase trước có dạng:

```json
{
  "text": "Dạ em gửi ảnh mẫu này cho anh/chị ạ.",
  "images": [
    "https://lh3.googleusercontent.com/d/IMAGE_ID_1",
    "https://lh3.googleusercontent.com/d/IMAGE_ID_2"
  ]
}
```

## Ngoài phạm vi Phase 3

- Fallback media send chi tiết nằm ở Phase 4 và đã được triển khai ở service gửi Facebook.
- Không download/rehost ảnh.
- Không thêm queue/outbox.
- Không gửi quá 3 ảnh theo phương án mới.

## File chính dự kiến sửa

- [app/api/v1/facebook_webhook.py](../../app/api/v1/facebook_webhook.py)
- [app/api/v1/response_message.py](../../app/api/v1/response_message.py)
- [app/services/facebook_message_service.py](../../app/services/facebook_message_service.py)
- [tests/test_facebook_message_service.py](../../tests/test_facebook_message_service.py)
- [tests/test_facebook_webhook_forward.py](../../tests/test_facebook_webhook_forward.py)

## Checklist

### 1. Gửi text trước

- [x] Build payload `message.text`.
- [x] Dùng đúng `recipient.id` là PSID khách.
- [x] Dùng `messaging_type` theo behavior hiện tại.
- [x] Không gửi text rỗng nếu không có nội dung.
- [x] Nếu gửi text lỗi, log lỗi rút gọn và xử lý theo behavior hiện tại.

Kết quả mong muốn:
  Khách nhận phần trả lời bằng chữ trước ảnh.

### 2. Gửi ảnh sau

- [x] Nếu có 1 ảnh, có thể gửi bằng `message.attachment`.
- [x] Nếu có nhiều ảnh, ưu tiên gửi bằng `message.attachments`.
- [x] Mỗi attachment có `type=image`.
- [x] Mỗi attachment có `payload.url`.
- [x] Không gửi quá 3 ảnh trong một lượt.
- [x] Loại duplicate URL trước khi gửi.

Kết quả mong muốn:
  Ảnh được gửi bằng media message, không bị dán raw URL trong text.

### 3. Validate image URL

- [x] Chỉ nhận URL scheme `https`.
- [x] Chỉ nhận host/pattern do BE tạo: `lh3.googleusercontent.com/d/{id}`.
- [x] Bỏ qua URL không hợp lệ.
- [x] Log số ảnh hợp lệ và số ảnh bị skip.

Kết quả mong muốn:
  BE không trở thành nơi gửi URL tùy ý lên Facebook.

### 4. Giữ tương thích luồng text hiện tại

- [x] Response không có ảnh vẫn gửi text như cũ.
- [x] Response chỉ có ảnh vẫn có behavior rõ.
- [x] Không làm thay đổi webhook verify.
- [x] Không làm thay đổi logic pause/admin takeover hiện tại nếu có.

Kết quả mong muốn:
  Luồng ảnh mới không làm regress luồng chat text đang chạy.

### 5. Test gửi Facebook

- [x] Test chỉ có text.
- [x] Test text + 1 ảnh.
- [x] Test text + nhiều ảnh.
- [x] Test text được gửi trước ảnh.
- [x] Test payload `message.attachment`.
- [x] Test payload `message.attachments`.
- [x] Test không gửi quá 3 ảnh.

Kết quả mong muốn:
  Thứ tự gửi và payload Facebook được cover bằng test.

## Acceptance criteria

- [x] BE gửi text trước.
- [x] BE gửi ảnh sau.
- [x] Payload Facebook đúng schema.
- [x] Không gửi raw Drive link trong text.
- [x] Không gửi quá 3 ảnh.

## Ghi chú mở

- Nếu thực tế `message.attachments` không ổn định với Page/API version đang dùng, Phase 4 sẽ fallback sang gửi từng ảnh bằng `message.attachment`.
