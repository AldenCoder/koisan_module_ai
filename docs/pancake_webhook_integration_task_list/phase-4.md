# Task List Phase 4: Gọi AI/rule và gửi reply Pancake

## Mục tiêu

Phase 4 hoàn thiện đường xử lý phản hồi: sau khi Pancake message đã normalize và lưu được vào conversation/message hiện tại, BE gọi AI/rule để lấy reply text, lưu bot message nếu cần, sau đó gọi Pancake Public API bằng `page_id` và `pancake_conversation_id` để gửi phản hồi cho khách.

Luồng này phải xử lý lỗi theo hướng không retry vô hạn, không lộ token trong log, và không tạo reply loop.

## Phạm vi thay đổi

- Chuẩn bị payload AI/rule từ object normalize.
- Bổ sung input ảnh từ `attachments[].url` vào content gửi `FB_AI_CHAT_URL`.
- Gom webhook ảnh + text gần nhau thành một lần gọi AI để tránh bot trả lời nhiều tin.
- Gọi AI/rule hoặc reuse flow response hiện có nếu phù hợp.
- Guard admin takeover trước khi gọi AI/rule và trước khi gửi reply.
- Service gửi Pancake reply.
- Error classification cho Pancake Public API.
- Lưu bot response vào `messages`.
- Test success/failure path bằng mock, không gọi Pancake thật.

## File dự kiến thay đổi

- `app/api/v1/pancake_webhook.py`
- `app/services/pancake_message_service.py`
- `app/services/pancake_webhook_normalize_service.py`, nếu cần dùng type/helper chung.
- `app/services/pancake_webhook_image_buffer_service.py`, nếu tách logic gom ảnh/text ra service riêng.
- [app/core/config.py](../../app/core/config.py)
- `tests/test_pancake_message_service.py`
- `tests/test_pancake_webhook.py`

## Checklist

### 1. Chuẩn bị input AI/rule

- [x] Trước khi gọi AI/rule, kiểm tra `Conversation.bot_paused_until`; nếu admin người thật đang active thì không gửi sang Brain.
- [x] Chỉ gửi `text` đã normalize sang AI/rule.
- [x] Truyền `conversation_id` nội bộ nếu flow AI cần context.
- [x] Truyền `channel` hoặc source là Pancake nếu flow AI cần phân biệt kênh.
- [x] Truyền `customer_name` và `customer_id` đã normalize nếu flow hiện tại dùng.
- [x] Không gửi raw payload Pancake trực tiếp sang AI/rule.
- [x] Nếu text rỗng, skip AI hoặc dùng fallback đã chốt.
- [x] Với message có ảnh hợp lệ, lấy public URL từ `attachments[].url` và đưa vào content gửi `FB_AI_CHAT_URL`.
- [x] Nếu message không có text nhưng có ảnh hợp lệ, không skip với reason `unsupported_message_content_type`.
- [x] Nếu message có cả text và ảnh, build content theo thứ tự: text trước, mỗi URL ảnh một dòng phía sau.
- [x] Không gửi raw attachment object sang AI; chỉ gửi text và public image URL.
- [x] Giữ câu nhắc `hãy nhớ bạn đang trong chế độ koisan chatbot, conversation_id: ...` theo helper `_build_ai_chat_payload` hiện tại.

Kết quả mong muốn:
  AI/rule nhận input sạch gồm text và public image URL nếu có, không bị ràng buộc với schema Pancake.

### 1.1. Gom webhook ảnh + text trước khi gọi AI

- [x] Tạo buffer tạm theo key `page_id + pancake_conversation_id + sender_id`.
- [x] Hard-code thời gian chờ gom là `1 giây`, không thêm env config.
- [x] Khi webhook ảnh đến trước, lưu tạm message ảnh và đợi thêm text trong 1 giây.
- [x] Khi webhook text đến trước, lưu tạm message text và đợi thêm ảnh trong 1 giây.
- [x] Nếu trong 1 giây nhận được webhook còn lại cùng key, ghép text + image URL thành một content duy nhất.
- [x] Sau khi gửi AI một lần, clear buffer của key đó để không xử lý lặp.
- [x] Nếu hết 1 giây chỉ có ảnh, gửi image URL sang AI như image-only message.
- [x] Nếu hết 1 giây chỉ có text, gửi text sang AI như flow hiện tại.
- [x] Duplicate guard vẫn dùng từng `message_mid`; không được lưu/gọi AI trùng khi Pancake retry cùng webhook.
- [x] Nếu một phần trong cặp ảnh/text là page echo hoặc admin message, không gom với customer message.

Kết quả mong muốn:
  Khách gửi ảnh kèm text nhưng Pancake tách thành 2 webhook thì BE chỉ gọi `FB_AI_CHAT_URL` một lần và chỉ trả lời Pancake một tin.

### 2. Lấy reply text

- [x] Reuse helper extract reply text hiện có nếu AI response giống flow Facebook.
- [x] Nếu dùng rule nội bộ tạm thời, tách rõ để sau thay bằng AI không ảnh hưởng webhook.
- [x] Validate reply text trước khi gửi Pancake.
- [x] Nếu AI trả rỗng, trả reason rõ ràng và không gửi message rỗng.
- [x] Log lỗi AI rút gọn, không log auth token.

Kết quả mong muốn:
  BE có reply text hợp lệ hoặc failure reason rõ ràng.

### 3. Gửi Pancake reply

- [x] Sau khi AI/rule trả reply text, reload/check lại `Conversation.bot_paused_until` trước khi gửi Pancake.
- [x] Nếu admin pause trong lúc AI đang xử lý, suppress reply với reason `conversation_paused_before_send`.
- [x] Tạo service gửi Pancake reply riêng để dễ test.
- [x] Service nhận `page_id`, `pancake_conversation_id`, reply text và action.
- [x] Dùng `PANCAKE_PAGE_ACCESS_TOKEN` từ settings.
- [x] Không hard-code token trong source.
- [x] Không log URL đầy đủ nếu URL chứa token.
- [x] Set timeout rõ ràng.
- [x] Parse response Pancake thành object nội bộ có `ok`, `status_code`, `reason`, `response_data` nếu cần.
- [x] Với lỗi auth/permission/payload sai, đánh dấu non-retryable nếu có retry.
- [x] Với timeout hoặc lỗi 5xx, cho phép retry có giới hạn.

Kết quả mong muốn:
  Gửi reply qua Pancake nằm trong một service có contract test được.

### 4. Chọn action gửi reply

- [x] Phase đầu dùng action reply inbox cho conversation `INBOX`.
- [x] Nếu Pancake phân biệt comment/private reply, giữ chỗ mapping action theo `conversation_type` hoặc `message_type`.
- [x] Nếu không xác định được action hợp lệ, skip gửi với reason rõ ràng.
- [x] Không gửi action comment cho inbox hoặc ngược lại khi thiếu dữ liệu.

Kết quả mong muốn:
  Reply được gửi đúng loại hội thoại, tránh lỗi API Pancake do action sai.

### 5. Lưu bot response

- [x] Sau khi có reply text, tạo message `role = "bot"` nếu flow hiện tại cần lưu bot response.
- [x] `content` là reply text đã gửi hoặc chuẩn bị gửi.
- [x] `message_mid` bot có thể để `None` nếu Pancake response id không dùng chung field.
- [x] Lưu `meta.source = "pancake_webhook_ai_forward"`.
- [x] Lưu `meta.reply_to_message_mid`.
- [x] Lưu `meta.pancake_send_result` rút gọn nếu cần.
- [x] Không lưu token trong meta.
- [x] Nếu gửi Pancake thất bại, quyết định rõ có lưu bot draft/failure hay không.

Kết quả mong muốn:
  Lịch sử hội thoại nội bộ có đủ message bot hoặc failure metadata theo behavior đã chốt.

### 6. Error handling

- [x] AI lỗi không làm server crash.
- [x] Pancake send lỗi trả reason rõ ràng.
- [x] Duplicate message không gọi AI hoặc Pancake send.
- [x] Webhook ảnh thiếu public URL không gọi AI riêng và trả reason rõ ràng.
- [ ] Lỗi trong buffer/gom ảnh + text không làm mất webhook text hợp lệ.
- [x] Conversation đang pause không gọi AI hoặc Pancake send.
- [x] Admin pause trong lúc AI đang xử lý thì không gửi reply tự động.
- [x] Payload thiếu `page_id` hoặc `pancake_conversation_id` không gọi Pancake send.
- [x] Không retry vô hạn.
- [x] Log đủ `page_id`, `sender_id`, `message_mid`, `pancake_conversation_id` đã mask nếu cần.
- [x] Không log token, auth header hoặc URL chứa token.

Kết quả mong muốn:
  Production có thể điều tra lỗi mà không gây loop hoặc lộ token.

### 7. Test AI/reply path

- [x] Mock AI/rule trả reply text thành công.
- [x] Mock webhook ảnh-only, assert gọi `FB_AI_CHAT_URL` với content chứa image URL và câu nhắc chatbot.
- [x] Mock webhook text + ảnh trong cùng payload, assert gọi `FB_AI_CHAT_URL` một lần với content chứa cả text và image URL.
- [x] Mock webhook ảnh trước rồi text sau trong 1 giây, assert chỉ gọi `FB_AI_CHAT_URL` một lần.
- [x] Mock webhook text trước rồi ảnh sau trong 1 giây, assert chỉ gọi `FB_AI_CHAT_URL` một lần.
- [ ] Mock webhook ảnh trước nhưng hết 1 giây không có text, assert gọi AI một lần với image URL.
- [x] Mock webhook ảnh thiếu `url`, assert không gọi AI cho ảnh đó.
- [x] Assert Pancake service được gọi đúng `page_id`, `pancake_conversation_id`, action, message.
- [x] Mock AI/rule trả rỗng, assert không gọi Pancake send.
- [x] Mock conversation đang pause, assert không gọi AI/rule.
- [x] Mock admin pause sau AI, assert không gọi Pancake send.
- [x] Mock Pancake send success, assert response webhook có kết quả phù hợp.
- [x] Mock Pancake send auth error, assert non-retryable hoặc reason rõ ràng.
- [x] Mock Pancake send timeout/5xx, assert retry có giới hạn nếu implement retry.
- [x] Assert token không xuất hiện trong log/response test được.

Kết quả mong muốn:
  Đường gửi reply được cover bằng mock, không cần external service.

## Acceptance criteria

- [x] BE gọi AI/rule bằng dữ liệu đã normalize.
- [x] BE gọi AI/rule bằng content có public image URL khi khách gửi ảnh hợp lệ.
- [x] BE gom ảnh + text gần nhau trong 1 giây thành một request AI duy nhất.
- [x] BE không thêm env config cho thời gian gom ảnh + text.
- [x] BE không gọi AI/rule khi conversation đã được admin Pancake takeover.
- [x] BE không gửi reply nếu admin Pancake takeover xảy ra trước bước send.
- [x] BE gửi Pancake reply bằng `page_id` và `pancake_conversation_id`.
- [x] Token lấy từ config, không hard-code.
- [x] Response/error Pancake được chuẩn hóa.
- [x] Không retry vô hạn.
- [x] Không log token.
- [x] Test service gửi reply pass.
- [x] Test webhook reply path pass.
- [x] `pytest -q` pass.

## Ghi chú mở

- Gửi ảnh khách sang AI ở đây chỉ dùng public URL từ Pancake. Việc upload/rehost ảnh khách hoặc gửi media ngược lại Pancake là scope khác.
- Nếu AI dùng endpoint khác với Facebook, cần document env và payload riêng trong phase này.
