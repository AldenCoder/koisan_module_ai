# Task List Phase 1: Bổ sung model/schema conversation

## Mục tiêu

Phase 1 bổ sung field `order_note` và status `order_pending` vào model/schema conversation. Thay đổi phải tương thích conversation cũ không có `order_note`.

Kết quả mong muốn:

- `Conversation` có field `order_note` optional.
- Status `order_pending` hợp lệ trong model và schema.
- API response conversation trả được `order_note`.
- API list/detail conversation có thể hiển thị note cho dashboard.

## Đầu vào đã chốt

- `order_note` nằm trực tiếp trên collection `conversations`.
- `order_note` là text optional.
- Conversation cũ thiếu field này vẫn hợp lệ.
- `order_pending` là status mới cho ghi chú đơn hàng cần sale xử lý.
- Không thêm bảng mới trong phase này.

## Ngoài phạm vi Phase 1

- Không tạo endpoint `order-notes`.
- Không implement append note.
- Không sửa webhook gửi `conversation_id`.
- Không sửa logic clear note khi sale xử lý xong.
- Không thêm UI dashboard.

## File chính dự kiến sửa

- [app/models/conversations.py](../../app/models/conversations.py)
- [app/api/schemas/conversation.py](../../app/api/schemas/conversation.py)
- [app/api/v1/conversations.py](../../app/api/v1/conversations.py)
- [app/services/conversation_service.py](../../app/services/conversation_service.py)

## Checklist

### 1. Cập nhật model

- [x] Thêm `ORDER_PENDING = "order_pending"` vào `ConversationStatus`.
- [x] Thêm field `order_note` vào `Conversation`.
- [x] Dùng `Optional[str]`.
- [x] Dùng `Field(default=None, max_length=...)` với giới hạn hợp lý.
- [x] Không thêm index cho `order_note`.
- [x] Giữ index `status` hiện tại để filter theo `order_pending`.
- [x] Đảm bảo conversation cũ không có field vẫn load được.

Kết quả mong muốn:
  Model nhận được trạng thái và field mới mà không cần migration bắt buộc.

### 2. Cập nhật schema response

- [x] Thêm `ORDER_PENDING = "order_pending"` vào `ConversationStatusSchema`.
- [x] Thêm `ORDER_PENDING = "order_pending"` vào `ConversationListStatusFilterSchema` nếu dashboard cần filter.
- [x] Thêm `order_note` vào `ConversationInfoResponse`.
- [x] Đảm bảo `ConversationListItemResponse` kế thừa được `order_note`.
- [x] Đảm bảo `ConversationDetailResponse` trả được `order_note`.
- [x] Không thêm `order_note` vào create request nếu không muốn client nhập trực tiếp qua CRUD conversation.
- [x] Không thêm `order_note` vào update request nếu chỉ cho clear bằng status lifecycle.

Kết quả mong muốn:
  Client đọc được note, nhưng write path chính vẫn là API order note.

### 3. Cập nhật serializer

- [x] Update `_serialize_conversation`.
- [x] Trả `order_note` bằng `getattr(conversation, "order_note", None)`.
- [x] Đảm bảo conversation thiếu field không lỗi serialize.
- [x] Đảm bảo status serialize đúng string `order_pending`.

Kết quả mong muốn:
  List/detail/create/update response không lỗi với field mới.

### 4. Cập nhật status validation

- [x] Update `_normalize_conversation_status`.
- [x] Error message liệt kê `order_pending` là giá trị hợp lệ.
- [x] Đảm bảo filter list chấp nhận `status=order_pending` nếu schema cho phép.
- [x] Không thay đổi behavior các status hiện tại ngoài phần cần thiết.

Kết quả mong muốn:
  Service layer không reject status mới.

## Acceptance criteria

- [x] Model có `order_note`.
- [x] Model có status `order_pending`.
- [x] Schema response trả `order_note`.
- [x] List/detail conversation không lỗi với conversation cũ.
- [x] Status validation chấp nhận `order_pending`.

## Ghi chú mở

- Nếu dashboard cần nhập note thủ công, mở task riêng để cho phép update `order_note` qua API admin. Phase này chỉ phục vụ AI append note.
