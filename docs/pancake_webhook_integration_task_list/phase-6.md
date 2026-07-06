# Task List Phase 6: Xử lý ảnh khách gửi từ webhook

## Mục tiêu

Phase 6 bổ sung khả năng xử lý ảnh khách gửi qua Pancake inbox. Khi Pancake webhook có attachment ảnh hợp lệ, BE lấy public image URL từ `data.message.attachments[].url`, lưu metadata ảnh vào `Message.meta.attachments`, rồi gửi URL ảnh sang `FB_AI_CHAT_URL` như nội dung message.

Trường hợp khách gửi ảnh kèm text nhưng Pancake tách thành 2 webhook sát nhau, BE phải gom trong cửa sổ chờ cố định 1 giây theo `page_id`, `pancake_conversation_id`, `sender_id`, sau đó chỉ gọi `FB_AI_CHAT_URL` một lần với cả text và image URL.

## Phạm vi thay đổi

- Detect attachment ảnh từ webhook Pancake.
- Normalize thêm `image_urls` từ `attachments[].url`.
- Lưu nguyên metadata attachment ảnh vào database.
- Coi image-only message có public URL là message hợp lệ.
- Buffer/gom webhook ảnh + text gần nhau trong 1 giây, hard-code trong code.
- Build content gửi `FB_AI_CHAT_URL` từ text và public image URL.
- Không upload/rehost ảnh trong phase này.
- Không thêm env config mới cho thời gian chờ gom.
- Test đầy đủ image-only, text+image cùng webhook, text+image tách webhook.

## File dự kiến thay đổi

- `app/services/pancake_webhook_normalize_service.py`
- `app/api/v1/pancake_webhook.py`
- `app/services/pancake_webhook_image_buffer_service.py`, nếu tách logic buffer/gom ra service riêng.
- `tests/test_pancake_webhook.py`
- `docs/pancake_webhook_integration.md`
- `docs/pancake_webhook_integration_task_list/phase-4.md`
- `docs/pancake_webhook_integration_task_list/phase-6.md`

## Checklist

### 1. Detect và normalize ảnh

- [x] Đọc `data.message.attachments` từ raw payload Pancake.
- [x] Xác định ảnh hợp lệ khi `type` thuộc nhóm `photo` hoặc `image`.
- [x] Chỉ lấy attachment ảnh có `url` public không rỗng.
- [x] Normalize danh sách public URL vào field nội bộ `image_urls`.
- [x] Giữ nguyên `attachments` trong object normalized để lưu metadata.
- [x] Không coi placeholder text của Pancake cho ảnh là text khách nhập thật nếu normalize hiện tại đã xác định `text_present = false`.
- [x] Nếu attachment không phải ảnh, chưa xử lý trong phase này và trả reason rõ ràng nếu message không có text hợp lệ.

Kết quả mong muốn:
  Object normalized có đủ `attachments` và `image_urls` để các bước sau không phải đọc raw payload.

### 2. Lưu metadata ảnh vào database

- [x] Lưu message ảnh của khách với `role = "user"`.
- [x] Lưu `message_mid` theo id message Pancake để chống trùng.
- [x] Lưu `meta.attachments` đúng shape Pancake trả về, gồm `image_data`, `type`, `url`.
- [x] Lưu `meta.image_urls` nếu cần debug nhanh danh sách URL ảnh đã trích xuất.
- [x] Lưu đủ `page_id`, `sender_id`, `pancake_conversation_id`, `timestamp` như flow text hiện tại.
- [x] Không lưu token hoặc auth header vào meta.
- [x] Nếu ảnh thiếu `url`, vẫn có thể lưu metadata để audit nhưng không gọi AI cho ảnh đó.

Kết quả mong muốn:
  Database có đủ metadata để audit ảnh khách gửi và vẫn giữ duplicate guard bằng `message_mid`.

### 3. Buffer/gom webhook ảnh + text

- [x] Tạo key gom bằng `page_id + pancake_conversation_id + sender_id`.
- [x] Hard-code thời gian chờ gom là `1 giây`.
- [x] Không thêm biến env mới cho thời gian chờ.
- [x] Khi nhận webhook ảnh, đưa message vào buffer theo key và chờ 1 giây trước khi gọi AI.
- [x] Khi nhận webhook text, đưa message vào buffer theo key và chờ 1 giây trước khi gọi AI.
- [x] Nếu trong 1 giây có cả text và ảnh cùng key, merge thành một payload AI duy nhất.
- [x] Nếu có nhiều ảnh cùng key trong cửa sổ chờ, đưa tất cả URL ảnh hợp lệ vào content, mỗi URL một dòng.
- [x] Nếu hết 1 giây chỉ có text, xử lý như flow text hiện tại.
- [x] Nếu hết 1 giây chỉ có ảnh, xử lý như image-only message.
- [x] Sau khi flush buffer, clear state của key để tránh gửi lặp.
- [x] Duplicate retry cùng `message_mid` không được làm buffer gửi AI lần hai.
- [x] Không gom customer message với page echo hoặc admin message.

Kết quả mong muốn:
  Khách gửi ảnh kèm text chỉ tạo một request `FB_AI_CHAT_URL` và một reply Pancake.

### 4. Build content gửi FB_AI_CHAT_URL

- [x] Với image-only, content bắt đầu bằng public image URL.
- [x] Với text + ảnh, content theo thứ tự: text khách gửi trước, sau đó các URL ảnh.
- [x] Mỗi URL ảnh đặt trên một dòng riêng.
- [x] Không serialize toàn bộ attachment JSON vào content gửi AI.
- [x] Giữ helper `_build_ai_chat_payload` hiện tại để append câu nhắc chatbot và `conversation_id`.
- [x] Payload gửi AI vẫn giữ shape:

```json
{
  "user": "<sender_id>",
  "messages": [
    {
      "role": "user",
      "content": "<text nếu có>\n<image_url nếu có>\n\nhãy nhớ bạn đang trong chế độ koisan chatbot, conversation_id: <conversation_id>"
    }
  ],
  "stream": false
}
```

Kết quả mong muốn:
  AI nhận một content rõ ràng, đủ text và ảnh, không phụ thuộc schema raw Pancake.

### 5. Gọi AI và gửi reply

- [x] Image-only message có public URL không trả `unsupported_message_content_type`.
- [x] Text + ảnh đã gom chỉ gọi `_post_ai_chat_with_retry` một lần.
- [x] Nếu AI trả reply hợp lệ, dùng flow gửi reply Pancake hiện tại.
- [x] Nếu AI lỗi, trả reason `ai_call_failed` như flow hiện tại.
- [x] Nếu conversation bị pause trước khi flush buffer, không gọi AI.
- [ ] Nếu admin pause trong lúc chờ buffer hoặc trong lúc AI xử lý, không gửi reply tự động.
- [x] Nếu ảnh thiếu public URL và không có text, không gọi AI và reason phải thể hiện rõ thiếu image URL.

Kết quả mong muốn:
  Luồng ảnh reuse được guard, AI call, send reply, error handling hiện tại mà không tạo reply loop.

### 6. Test normalize và persistence

- [x] Test webhook ảnh inbox normalize ra `attachment_count = 1`.
- [x] Test attachment `type = photo` + `url` tạo `image_urls`.
- [x] Test attachment `type = image` + `url` tạo `image_urls`.
- [x] Test attachment ảnh thiếu `url` không tạo `image_urls`.
- [x] Test `_save_pancake_user_message` lưu `meta.attachments` đủ `image_data`, `type`, `url`.
- [x] Test image-only có public URL vẫn lưu message user.
- [x] Test image-only thiếu public URL lưu/audit theo behavior đã chọn nhưng không gọi AI.

Kết quả mong muốn:
  Normalize và lưu DB đúng với payload ảnh thực tế từ Pancake.

### 7. Test buffer/gom và AI call

- [x] Test ảnh trước, text sau trong 1 giây: chỉ gọi AI một lần.
- [x] Test text trước, ảnh sau trong 1 giây: chỉ gọi AI một lần.
- [x] Test content AI trong case gom có cả text và image URL đúng thứ tự.
- [ ] Test hết 1 giây chỉ có ảnh: gọi AI một lần với image URL.
- [ ] Test hết 1 giây chỉ có text: giữ behavior text hiện tại.
- [ ] Test hai conversation khác nhau không bị gom nhầm.
- [ ] Test hai sender khác nhau trong cùng page không bị gom nhầm.
- [ ] Test retry duplicate `message_mid` không gọi AI lại.
- [ ] Test page echo/admin message không vào buffer customer message.

Kết quả mong muốn:
  Cơ chế chờ 1 giây giải quyết được case Pancake tách ảnh/text mà không làm sai luồng khác.

### 8. Test lỗi và regression

- [x] Test ảnh thiếu `url` không gọi `FB_AI_CHAT_URL`.
- [x] Test attachment không phải ảnh không gọi AI nếu không có text.
- [x] Test conversation đang pause không gọi AI dù có ảnh.
- [ ] Test admin pause trong lúc chờ buffer thì suppress AI/reply.
- [x] Test AI trả rỗng không gửi Pancake reply.
- [x] Test Pancake send lỗi vẫn trả reason rõ ràng.
- [x] Chạy `pytest -q`.
- [x] Không chạy `pre-commit` theo guideline repo.

Kết quả mong muốn:
  Luồng ảnh không làm regress text message, admin takeover, duplicate guard và Pancake reply.

## Acceptance criteria

- [x] BE nhận diện được ảnh Pancake qua `attachments[].type = photo/image`.
- [x] BE lấy public image URL từ `attachments[].url`.
- [x] BE lưu nguyên attachment ảnh vào `Message.meta.attachments`.
- [x] Image-only message có public URL được coi là message hợp lệ.
- [x] Text + ảnh trong cùng webhook gửi một request AI có cả text và image URL.
- [x] Text + ảnh tách thành 2 webhook gần nhau được gom trong 1 giây và gửi một request AI.
- [x] Thời gian gom 1 giây hard-code trong code, không thêm env config.
- [x] Ảnh thiếu public URL không gọi AI.
- [x] Bot không trả lời thành 2 tin cho case khách gửi ảnh kèm text.
- [x] `pytest -q` pass.

## Ghi chú mở

- Nếu sau này cần upload/rehost ảnh khách gửi, mở task riêng để tránh làm phức tạp phase này.
- Nếu Pancake thay đổi field URL ảnh, cập nhật normalize và test theo raw payload mới.
- Nếu production cần gom qua nhiều process/instance, buffer in-memory có thể không đủ; khi đó cần cân nhắc queue/cache dùng chung.
