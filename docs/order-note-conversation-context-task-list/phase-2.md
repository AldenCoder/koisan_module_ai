# Task List Phase 2: API và service create order_notes

## Mục tiêu

Phase 2 tạo API `POST /api/v1/order-notes` và service lưu note vào đúng conversation. Endpoint này là write path chính để AI Agent gửi ghi chú đơn hàng về BE.

Kết quả mong muốn:

- API nhận đúng 2 field `conversation_id` và `order_note`.
- BE chỉ update khi tìm đúng conversation bằng `conversation_id`.
- Note đầu tiên ghi dạng `1. [HH:mm] ...`.
- Note tiếp theo append dạng `2. [HH:mm] ...`.
- Conversation được set `status = "order_pending"`.

## Đầu vào đã chốt

- Không có `channel`, `customer_id`, `message_id`, `request_id` trong body.
- Không fallback nếu `conversation_id` sai.
- Không chống duplicate trong phase này.
- Log warning khi `conversation_id` invalid hoặc not found.

## Ngoài phạm vi Phase 2

- Không clear note khi sale xử lý xong.
- Không sửa context message gửi sang AI.
- Không thêm bảng order.
- Không thêm idempotency.
- Không gọi service ngoài.

## File chính dự kiến sửa

- `app/api/schemas/order_note.py`, nếu tách schema riêng.
- `app/api/v1/order_notes.py`, nếu tách router riêng.
- [app/api/router_v1.py](../../app/api/router_v1.py)
- [app/services/conversation_service.py](../../app/services/conversation_service.py), nếu reuse service conversation.
- `app/services/order_note_service.py`, nếu tách service riêng.

## Checklist

### 1. Tạo schema request/response

- [x] Tạo `OrderNoteCreateRequest`.
- [x] Field `conversation_id: str`.
- [x] Field `order_note: str`.
- [x] Validate `conversation_id` không rỗng sau khi trim.
- [x] Validate `order_note` không rỗng sau khi trim.
- [x] Không khai báo thêm field trong request body.
- [x] Tạo `OrderNoteCreateResponse`.
- [x] Response có `success`.
- [x] Response có `conversation_id`.
- [x] Response có `status`.
- [x] Response có `order_note`.
- [x] Response có `order_note_index`.

Kết quả mong muốn:
  Contract rõ ràng cho AI Agent và dễ test bằng unit test schema/API.

### 2. Tạo helper format note

- [x] Tạo helper normalize note text.
- [x] Tạo helper format timestamp `HH:mm` bằng `now_vn()`.
- [x] Tạo helper đếm số dòng note hiện có bằng pattern `^\d+\.`.
- [x] Nếu note hiện tại rỗng, next index là `1`.
- [x] Nếu note hiện tại có 3 dòng đánh số, next index là `4`.
- [x] Format dòng mới là `{index}. [HH:mm] {note}`.
- [x] Append bằng newline khi đã có note cũ.

Kết quả mong muốn:
  Logic append tách nhỏ, dễ test và không phụ thuộc API layer.

### 3. Tạo service lưu order_note

- [x] Tạo `create_order_note_service`.
- [x] Trim `conversation_id`.
- [x] Trim `order_note`.
- [x] Lookup conversation bằng `Conversation.get(conversation_id)` hoặc helper hiện có.
- [x] Nếu id sai format, raise lỗi tương ứng để API trả `400`.
- [x] Nếu conversation không tồn tại, trả `None` hoặc raise lỗi để API trả `404`.
- [x] Không lookup bằng `customer_id`.
- [x] Không lookup bằng `channel`.
- [x] Không lookup conversation mới nhất.
- [x] Nếu conversation chưa `order_pending`, set note mới từ `1.`.
- [x] Nếu conversation đang `order_pending`, append dòng tiếp theo.
- [x] Set `conversation.status = ConversationStatus.ORDER_PENDING`.
- [x] Set `conversation.updated_at = now_vn()`.
- [x] Save conversation.
- [x] Return data đủ cho response.

Kết quả mong muốn:
  Service update đúng một conversation theo id và không có fallback mơ hồ.

### 4. Logging lỗi conversation_id

- [x] Log warning `ORDER_NOTE_CONVERSATION_ID_INVALID` khi id sai format.
- [x] Log warning `ORDER_NOTE_CONVERSATION_NOT_FOUND` khi không tìm thấy conversation.
- [x] Log có `conversation_id`.
- [x] Log không chứa toàn bộ `order_note` nếu note có thể chứa dữ liệu khách hàng nhạy cảm.
- [x] Đảm bảo hai lỗi trên không update DB.

Kết quả mong muốn:
  Vận hành debug được AI gửi sai id mà không làm lộ nội dung đơn hàng.

### 5. Tạo router API

- [x] Tạo router `order_notes`.
- [x] Expose `POST /api/v1/order-notes`.
- [x] Register router trong `app/api/router_v1.py`.
- [x] Map validation lỗi body thành `400` hoặc framework validation phù hợp.
- [x] Map invalid `conversation_id` thành `400`.
- [x] Map not found thành `404`.
- [x] Success trả `200` hoặc `201`.
- [x] Không thêm field nào khác vào body.

Kết quả mong muốn:
  AI Agent có endpoint ổn định để gọi.

## Acceptance criteria

- [x] Request chỉ có `conversation_id` và `order_note`.
- [x] Lần đầu set `order_pending` và note `1.`.
- [x] Lần sau append note `2.`.
- [x] Sai `conversation_id` không update DB.
- [x] Conversation không tồn tại không update DB.
- [x] Có warning log cho hai case lỗi id.

## Ghi chú mở

- Cần chốt dependency auth cho endpoint khi implement. Dù dùng auth kiểu nào, auth không nằm trong body payload.
