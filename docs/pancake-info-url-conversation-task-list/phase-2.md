# Task List Phase 2: Build URL và gắn vào create conversation

## Mục tiêu

Phase 2 tạo helper build `pancake_info_url` từ `page_id` và `pancake_conversation_id`, sau đó gắn helper vào nhánh tạo mới conversation trong flow Pancake webhook.

Kết quả mong muốn:

- BE build được URL theo đúng format.
- Conversation Pancake mới có `pancake_info_url`.
- Conversation đã tồn tại không bị overwrite field.
- Flow duplicate, pause, admin takeover và lưu message hiện tại không đổi.

## Đầu vào đã chốt

- `page_id` lấy từ `normalized["page_id"]`.
- `pancake_conversation_id` lấy từ `normalized["pancake_conversation_id"]`.
- URL format là `https://pancake.vn/{page_id}?c_id={pancake_conversation_id}`.
- Helper trả `None` nếu thiếu một trong hai field.

## Ngoài phạm vi Phase 2

- Không sửa normalize payload nếu flow hiện tại đã validate đủ field.
- Không đổi rule tìm conversation theo `sender_id`.
- Không backfill conversation cũ.
- Không thay đổi API gửi reply Pancake.

## File chính dự kiến sửa

- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)

Nếu tách helper riêng:

- `app/services/pancake_conversation_link_service.py`
- `tests/test_pancake_conversation_link_service.py`

## Checklist

### 1. Tạo helper build URL

- [x] Tạo helper nhận `page_id` và `pancake_conversation_id`.
- [x] Trim `page_id`.
- [x] Trim `pancake_conversation_id`.
- [x] Trả `None` nếu `page_id` rỗng.
- [x] Trả `None` nếu `pancake_conversation_id` rỗng.
- [x] Trả URL đúng format khi đủ dữ liệu.
- [x] Không thêm token hoặc auth data vào URL.

Kết quả mong muốn:
  Logic build URL nhỏ, dễ test và không phụ thuộc database.

### 2. Gắn vào `_get_or_create_pancake_conversation`

- [x] Gọi helper trong nhánh `conversation is None`.
- [x] Set `pancake_info_url` khi khởi tạo `Conversation`.
- [x] Insert conversation như flow hiện tại.
- [x] Không gọi helper trong nhánh conversation đã tồn tại.
- [x] Không update `conversation.pancake_info_url` ở nhánh đã tồn tại.
- [x] Không thay đổi logic update `channel` và `customer_name`.

Kết quả mong muốn:
  Field được tạo đúng một lần tại thời điểm insert conversation mới.

### 3. Giữ nguyên flow hiện tại

- [x] Duplicate check vẫn dùng `message_mid`.
- [x] Save user message vẫn lưu meta như hiện tại.
- [x] Reply Pancake vẫn dùng `page_id` và `pancake_conversation_id` hiện có.
- [x] Admin takeover không bị ảnh hưởng.
- [x] Bot pause không bị ảnh hưởng.

Kết quả mong muốn:
  Thay đổi chỉ bổ sung field vào conversation, không làm lệch behavior webhook.

## Acceptance criteria

- [x] Conversation Pancake mới được insert với `pancake_info_url` đúng format.
- [x] Conversation đã tồn tại không bị overwrite field.
- [x] Helper trả `None` khi thiếu input.
- [x] Flow Pancake hiện tại vẫn pass test.

## Ghi chú mở

- Nếu sau này muốn reuse helper ở script backfill, nên đặt helper ở service riêng thay vì để private trong router.
