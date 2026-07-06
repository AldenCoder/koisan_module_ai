# Task List Phase 4: Gửi conversation_id sang AI

## Mục tiêu

Phase 4 bổ sung `conversation_id` vào context message gửi sang AI Agent để AI có thể gọi `POST /api/v1/order-notes` với đúng conversation hiện tại.

Kết quả mong muốn:

- AI nhận được `conversation_id` theo từng conversation.
- Context note được gửi ở mỗi lượt message thường.
- Conversation cũ đã init vẫn nhận được `conversation_id`.
- Init/bootstrap đọc `SKILL.md` hiện tại không bị hỏng.

## Đầu vào đã chốt

- Context note mong muốn:

```text
hãy nhớ bạn đang trong chế độ koisan chatbot, conversation_id: {conversation_id}
```

- Nên gửi context note ở mỗi lượt message sang AI.
- Không chỉ dựa vào init một lần vì conversation cũ có thể đã initialized.
- Pancake đã tạo/lấy conversation trước khi gọi `_generate_pancake_reply`.

## Ngoài phạm vi Phase 4

- Không sửa nội dung `SKILL.md`.
- Không implement API order note trong phase này.
- Không đổi response format của AI.
- Không đổi endpoint `FB_AI_CHAT_URL`.
- Không thay đổi cách extract text từ AI response.

## File chính dự kiến sửa

- [app/api/v1/facebook_webhook.py](../../app/api/v1/facebook_webhook.py)
- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [tests/test_facebook_webhook_forward.py](../../tests/test_facebook_webhook_forward.py)
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)

## Checklist

### 1. Tách helper build context note

- [x] Tạo helper build note từ base text `hãy nhớ bạn đang trong chế độ koisan chatbot`.
- [x] Nếu có `conversation_id`, append `, conversation_id: {conversation_id}`.
- [x] Nếu không có `conversation_id`, giữ note cũ.
- [x] Trim `conversation_id`.
- [x] Không append `conversation_id` rỗng.
- [x] Không đổi `FB_AI_INIT_MESSAGE`.

Kết quả mong muốn:
  Có một chỗ duy nhất format context note để tránh lệch giữa Facebook và Pancake.

### 2. Cập nhật `_build_ai_chat_payload`

- [x] Cho `_build_ai_chat_payload` nhận optional `conversation_id`.
- [x] Message init vẫn không append test mode note như behavior hiện tại.
- [x] Message thường append context note như hiện tại.
- [x] Nếu có `conversation_id`, message thường append note có id.
- [x] Nếu không có `conversation_id`, message thường giữ payload cũ.
- [x] Không đổi shape payload `user`, `messages`, `stream`.

Kết quả mong muốn:
  Backward compatible cho call site cũ nhưng call site mới có thể truyền conversation id.

### 3. Cập nhật Pancake flow

- [x] Trong `_generate_pancake_reply`, lấy `conversation.id`.
- [x] Truyền `conversation_id=conversation.id` vào `_build_ai_chat_payload`.
- [x] Đảm bảo synthetic auto consult flow cũng truyền đúng conversation id vì dùng chung `_generate_pancake_reply`.
- [x] Đảm bảo duplicate/unsupported message không gọi AI như hiện tại.
- [x] Đảm bảo log không cần in toàn bộ payload AI.

Kết quả mong muốn:
  Mọi Pancake message gửi AI đều có context id của conversation nội bộ.

### 4. Cập nhật Facebook flow nếu áp dụng chung

- [x] Tìm các call `_build_ai_chat_payload` trong Facebook flow message thường.
- [x] Chỉ truyền `conversation.id` sau khi đã get/create conversation.
- [x] Không truyền id ở các call chưa có conversation.
- [x] Giữ init flow hoạt động.
- [x] Đảm bảo test cũ không fail vì optional argument.

Kết quả mong muốn:
  Shared helper hỗ trợ cả Facebook và Pancake nhưng không bắt buộc mọi call site phải có id ngay.

### 5. Contract gửi AI

- [x] Payload content cuối cùng có nội dung khách nhắn.
- [x] Payload content có dòng context note.
- [x] Context note chứa đúng `conversation_id`.
- [x] Không gửi `channel` hoặc `customer_id` thay cho `conversation_id`.
- [x] Không gửi thông tin nhạy cảm không cần thiết.

Kết quả mong muốn:
  AI có đủ id để gọi API order note, không phải suy luận từ thông tin khách.

## Acceptance criteria

- [x] `_build_ai_chat_payload` backward compatible khi không truyền `conversation_id`.
- [x] Pancake AI payload có `conversation_id`.
- [x] Init message hiện tại không bị đổi nội dung.
- [x] Auto consult Pancake vẫn dùng đúng context id.
- [x] Test payload mới pass.

## Ghi chú mở

- Nếu AI cần format machine-readable hơn, mở task riêng để chuyển context note sang block JSON/system metadata. Phase này giữ dạng text để ít sửa nhất.
