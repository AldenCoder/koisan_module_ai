# Task lưu order_note vào conversations và gửi conversation_id cho AI

## Mục tiêu

Tài liệu này mô tả task đơn giản để AI Agent có thể báo về BE khi khách có nhu cầu đặt hàng. BE không tạo order thật, chỉ lưu ghi chú đơn hàng vào `conversations.order_note` và đổi `conversations.status` sang `order_pending` để sale nhìn thấy và xử lý.

Task cũng bổ sung `conversation_id` vào context message gửi sang AI theo từng khách hàng/conversation. Khi AI cần gọi API tạo order note, AI dùng chính `conversation_id` này để gửi payload về BE.

## Nguyên tắc chính

- `order_note` chỉ là ghi chú cảnh báo cho sale, không phải dữ liệu đơn hàng chuẩn.
- Không thêm bảng order mới trong phase này.
- Không yêu cầu AI gửi `channel`, `customer_id`, `order_id` hoặc dữ liệu định danh khác.
- Payload API chỉ có 2 field: `conversation_id` và `order_note`.
- Nếu sale chưa xử lý mà khách đặt thêm/sửa thêm, BE append nội dung mới vào cùng `conversations.order_note`.
- Khi sale xác nhận đã xử lý xong, BE đổi status về `new` và xóa trắng `conversations.order_note`.

## API create order_notes

Endpoint đề xuất:

```text
POST /api/v1/order-notes
```

Request body chỉ gồm 2 trường:

```json
{
  "conversation_id": "1234......56789",
  "order_note": "Khách muốn đặt 2 ly matcha, giao lúc 15h, địa chỉ ..."
}
```

Validation:

- `conversation_id` bắt buộc, không được rỗng.
- `order_note` bắt buộc, trim khoảng trắng, không được rỗng.
- Nếu `conversation_id` sai format thì trả `400`, không update gì và log warning.
- Nếu không tìm thấy conversation thì trả `404`, không update gì và log warning.
- Nếu lưu thành công thì trả `200` hoặc `201`.

Response đề xuất:

```json
{
  "success": true,
  "conversation_id": "1234......56789",
  "status": "order_pending",
  "order_note": "1. [10:05] Khách muốn đặt 2 ly matcha, giao lúc 15h, địa chỉ ...",
  "order_note_index": 1
}
```

API này nên là endpoint nội bộ cho AI Agent. Phần xác thực có thể dùng cơ chế auth hiện có hoặc bearer token nội bộ, nhưng không thêm field auth vào body vì body cần giữ đúng 2 trường.

## Data model

Thêm field vào `Conversation`:

```python
order_note: Optional[str] = Field(default=None, max_length=...)
```

Thêm status mới:

```python
class ConversationStatus(str, Enum):
    NEW = "new"
    HANDOVER = "handover"
    ORDER_PENDING = "order_pending"
```

Schema response/list/update conversation cũng cần expose `order_note` và accept status `order_pending`.

Các vị trí cần kiểm tra khi implement:

- `app/models/conversations.py`
- `app/api/schemas/conversation.py`
- `app/services/conversation_service.py`
- `app/api/v1/conversations.py`

## Rule lưu order_note

Khi AI gọi `POST /api/v1/order-notes`, BE tìm conversation theo `conversation_id`.

BE chỉ update khi tìm đúng document `Conversation` bằng chính `conversation_id` trong payload. Nếu `conversation_id` sai format, không tồn tại, hoặc không lấy được conversation, BE dừng xử lý ngay:

```text
Không append order_note
Không đổi status
logger.warning báo sai/missing conversation_id
Trả lỗi 400 hoặc 404
```

Log event đề xuất:

```text
ORDER_NOTE_CONVERSATION_ID_INVALID conversation_id=...
ORDER_NOTE_CONVERSATION_NOT_FOUND conversation_id=...
```

Không fallback tìm conversation bằng `channel`, `customer_id`, tên khách, hoặc conversation mới nhất. Với payload 2 field, `conversation_id` là nguồn định danh duy nhất.

Nếu conversation chưa ở trạng thái `order_pending`:

```text
order_note = "1. [HH:mm] {order_note mới}"
status = "order_pending"
updated_at = now
```

Nếu conversation đang ở trạng thái `order_pending`:

```text
order_note = "{order_note hiện tại}\n{index tiếp theo}. [HH:mm] {order_note mới}"
status giữ nguyên "order_pending"
updated_at = now
```

Ví dụ sau 3 lần AI báo về trước khi sale xử lý:

```text
1. [10:05] Khách muốn đặt 2 ly matcha, giao lúc 15h.
2. [10:20] Khách đặt thêm 1 bánh tiramisu.
3. [10:35] Khách đổi địa chỉ giao hàng sang 12 Nguyễn Trãi.
```

Không thêm `order_note_count` trong phase này. Số thứ tự tiếp theo có thể tính bằng cách đếm các dòng trong `order_note` đang bắt đầu bằng pattern:

```text
^\d+\.
```

Nếu field `order_note` bị rỗng nhưng status đang là `order_pending`, BE coi như note đầu tiên và ghi lại từ `1.`.

## Rule sale xử lý xong

Khi sale xác nhận đã tạo đơn hàng hoặc đã xử lý xong ghi chú đơn hàng, dashboard/BE đổi status của conversation từ `order_pending` về `new` và xóa trắng `order_note`:

```text
status = "new"
order_note = null
```

Ví dụ:

```json
{
  "status": "new"
}
```

Kết quả:

```text
status = "new"
order_note = null
```

Nếu sau đó khách lại đặt tiếp và AI gọi `POST /api/v1/order-notes`, BE tạo lại note mới từ `1.` và đổi status về `order_pending`.

## Không xử lý duplicate trong phase này

Vì payload chỉ có `conversation_id` và `order_note`, BE không có key idempotency như `message_id`.

Do đó behavior đơn giản là:

```text
Mỗi request hợp lệ có conversation_id tìm thấy = append một dòng order_note.
```

Nếu AI retry cùng một request, BE có thể bị trùng note. Đây là trade-off chấp nhận được của phase đơn giản này. Nếu sau này cần chống trùng chắc hơn, mở task riêng để thêm `message_id` hoặc `request_id`.

## Gửi conversation_id trong message sang AI

Hiện Pancake đang tạo/lấy conversation trước khi gọi AI trong `app/api/v1/pancake_webhook.py`. Vì vậy sau bước tạo conversation, BE đã có `conversation.id` để gửi kèm sang AI.

Context note mong muốn:

```text
hãy nhớ bạn đang trong chế độ koisan chatbot, conversation_id: {conversation_id}
```

Payload gửi sang AI nên có dạng:

```text
{nội dung khách nhắn}

hãy nhớ bạn đang trong chế độ koisan chatbot, conversation_id: 1234......56789
```

Khuyến nghị gửi context note này ở mỗi lượt message sang AI, không chỉ gửi trong init/bootstrap một lần. Lý do:

- Conversation cũ có thể đã `fb_ai_initialized=True`, nên init không chạy lại.
- AI có thể cần `conversation_id` ngay ở lượt hiện tại để gọi API `order-notes`.
- Gửi kèm mỗi lượt giúp giảm phụ thuộc vào trí nhớ session phía AI.

## Điểm sửa bootstrap/context message

Hiện `app/api/v1/facebook_webhook.py` có:

```python
FB_AI_INIT_MESSAGE = (
    "Hãy đọc file markdown tại /data/workspace/koisan_chatbot_brain/SKILL.md và bắt đầu koisan chatbot."
)
FB_AI_TEST_MODE_NOTE = "hãy nhớ bạn đang trong chế độ koisan chatbot"
```

Và `_build_ai_chat_payload(...)` đang append `FB_AI_TEST_MODE_NOTE` vào message thường.

Phương án sửa ít:

1. Cho `_build_ai_chat_payload` nhận thêm optional `conversation_id`.
2. Nếu có `conversation_id`, build note thành:

```text
hãy nhớ bạn đang trong chế độ koisan chatbot, conversation_id: {conversation_id}
```

3. Nếu không có `conversation_id`, giữ behavior cũ.
4. Tại Pancake `_generate_pancake_reply`, gọi:

```python
payload = _build_ai_chat_payload(
    user=sender_id,
    content=text,
    conversation_id=conversation.id,
)
```

Nếu muốn áp dụng cho Facebook flow luôn, các call site bên Facebook cũng truyền `conversation.id` sau khi đã get/create conversation.

## Luồng tổng thể sau thay đổi

```text
Khách nhắn vào Pancake/Facebook
-> Webhook nhận message
-> BE normalize payload
-> BE tạo/lấy Conversation
-> BE có conversation.id
-> BE lưu user message như hiện tại
-> BE gửi message sang AI kèm conversation_id
-> AI tư vấn khách như hiện tại
-> Khi AI xác định khách muốn đặt/sửa/thêm đơn
-> AI gọi POST /api/v1/order-notes với conversation_id + order_note
-> BE append note vào conversations.order_note
-> BE set conversations.status = "order_pending"
-> Sale thấy conversation cần xử lý
-> Sale đổi status sau khi xử lý
-> BE clear conversations.order_note
```

## File task-list chi tiết

- [Phase 0: Chốt giải pháp order_note và conversation_id context](order-note-conversation-context-task-list/phase-0.md)
- [Phase 1: Bổ sung model/schema conversation](order-note-conversation-context-task-list/phase-1.md)
- [Phase 2: API và service create order_notes](order-note-conversation-context-task-list/phase-2.md)
- [Phase 3: Clear order_note khi sale xử lý xong](order-note-conversation-context-task-list/phase-3.md)
- [Phase 4: Gửi conversation_id sang AI](order-note-conversation-context-task-list/phase-4.md)
- [Phase 5: Test coverage](order-note-conversation-context-task-list/phase-5.md)
- [Phase 6: Rollout và vận hành](order-note-conversation-context-task-list/phase-6.md)

## Task list implement

### Phase 1. Conversation model/schema

- [x] Thêm `ORDER_PENDING = "order_pending"` vào `ConversationStatus`.
- [x] Thêm `ORDER_PENDING = "order_pending"` vào `ConversationStatusSchema`.
- [x] Nếu list filter cần lọc trạng thái chờ đơn, thêm `ORDER_PENDING` vào `ConversationListStatusFilterSchema`.
- [x] Thêm `order_note` vào model `Conversation`.
- [x] Thêm `order_note` vào response schema conversation.
- [x] Update serializer conversation để trả `order_note`.
- [x] Update status validation message để có `order_pending`.

### Phase 2. Service lưu order_note

- [x] Tạo request schema `OrderNoteCreateRequest` gồm `conversation_id`, `order_note`.
- [x] Tạo response schema `OrderNoteCreateResponse`.
- [x] Tạo service `create_order_note_service`.
- [x] Service tìm conversation theo `conversation_id`.
- [x] Nếu `conversation_id` sai format, không update conversation và log warning.
- [x] Nếu không tìm thấy conversation, không update conversation và log warning.
- [x] Không fallback sang `channel`, `customer_id` hoặc conversation mới nhất.
- [x] Nếu chưa `order_pending`, ghi note dạng `1. [HH:mm] ...`.
- [x] Nếu đang `order_pending`, append note dạng `{index}. [HH:mm] ...`.
- [x] Set `status = order_pending`.
- [x] Update `updated_at`.
- [x] Return `conversation_id`, `status`, `order_note`, `order_note_index`.

### Phase 3. API endpoint

- [x] Tạo router `app/api/v1/order_notes.py`.
- [x] Expose `POST /api/v1/order-notes`.
- [x] Register router trong `app/api/router_v1.py`.
- [x] Validate lỗi `400`, `404`.
- [x] Không yêu cầu field nào khác ngoài `conversation_id`, `order_note`.

### Phase 4. Clear order_note khi sale xử lý

- [x] Update `update_conversation_crud_service`.
- [x] Khi sale xử lý xong, update status từ `order_pending` về `new`.
- [x] Khi update status từ `order_pending` về `new`, set `order_note = None`.
- [x] Đảm bảo update các field khác không vô tình xóa `order_note`.

### Phase 5. Gửi conversation_id sang AI

- [x] Update `_build_ai_chat_payload` để nhận optional `conversation_id`.
- [x] Khi có `conversation_id`, append note `hãy nhớ bạn đang trong chế độ koisan chatbot, conversation_id: ...`.
- [x] Pancake `_generate_pancake_reply` truyền `conversation.id`.
- [x] Nếu áp dụng cho Facebook, các call site sau khi get/create conversation cũng truyền `conversation.id`.
- [x] Giữ init/bootstrap hiện tại hoạt động với conversation cũ.

### Phase 6. Tests

- [x] Test create order note lần đầu set status `order_pending`.
- [x] Test create order note lần hai append dòng `2.`.
- [x] Test conversation không tồn tại trả `404`.
- [x] Test conversation không tồn tại không update bất kỳ conversation nào và có warning log.
- [x] Test `conversation_id` sai format trả `400`, không update conversation và có warning log.
- [x] Test `order_note` rỗng trả `400`.
- [x] Test sale đổi status khỏi `order_pending` thì clear `order_note`.
- [x] Test `_build_ai_chat_payload` append đúng `conversation_id`.
- [x] Test Pancake gọi AI với payload có `conversation_id`.
- [x] Chạy `pytest -q`.

## Rollout notes

- Deploy BE có field/status mới trước khi cấu hình AI gọi API `order-notes`.
- Sau deploy, kiểm tra dashboard/list conversation đọc được status `order_pending`.
- Cập nhật instruction phía AI Agent: khi khách xác nhận đặt/sửa/thêm đơn, gọi `POST /api/v1/order-notes` bằng `conversation_id` trong context.
- Vì phase này không chống duplicate, cần theo dõi vài ngày đầu xem AI có retry gây note trùng hay không.
