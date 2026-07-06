# Task List Phase 3: Clear order_note khi sale xử lý xong

## Mục tiêu

Phase 3 cập nhật lifecycle của conversation khi sale xử lý xong ghi chú đơn hàng. Khi dashboard/BE đổi conversation từ `order_pending` về `new`, BE phải xóa trắng `order_note`.

Kết quả mong muốn:

- Sale xử lý xong thì `status = "new"`.
- Sale xử lý xong thì `order_note = null`.
- Các update profile khác không làm mất `order_note`.
- Khách đặt tiếp sau đó sẽ bắt đầu lại note từ `1.`.

## Đầu vào đã chốt

- `order_pending` chỉ là trạng thái cần sale xử lý.
- `new` là trạng thái bình thường sau khi xử lý xong.
- Không dùng status khác cho flow order note đơn giản này.
- `order_note` không phải lịch sử đơn hàng lâu dài.

## Ngoài phạm vi Phase 3

- Không tạo endpoint riêng để sale clear note.
- Không thêm audit table.
- Không lưu lịch sử note đã xử lý.
- Không sửa UI dashboard.
- Không sửa API create order note.

## File chính dự kiến sửa

- [app/services/conversation_service.py](../../app/services/conversation_service.py)
- [app/api/v1/conversations.py](../../app/api/v1/conversations.py)
- [tests/test_conversation_status_transitions.py](../../tests/test_conversation_status_transitions.py)
- [tests/test_conversations_api.py](../../tests/test_conversations_api.py)

## Checklist

### 1. Xác định transition cần clear note

- [x] Nếu current status là `order_pending` và new status là `new`, clear `order_note`.
- [x] Set `order_note = None`.
- [x] Set `updated_at = now_vn()`.
- [x] Save conversation.
- [x] Không clear note nếu status vẫn là `order_pending`.
- [x] Không clear note nếu chỉ update `channel`.
- [x] Không clear note nếu chỉ update `customer_name`.
- [x] Không clear note nếu chỉ update `customer_id`.
- [x] Không clear note nếu chỉ update `is_active`.

Kết quả mong muốn:
  Clear note chỉ xảy ra khi sale thật sự kết thúc trạng thái chờ xử lý đơn.

### 2. Cập nhật update service

- [x] Đọc current status trước khi apply update.
- [x] Normalize status mới bằng helper hiện có.
- [x] Khi status mới là `new`, kiểm tra current status có phải `order_pending`.
- [x] Nếu đúng, clear `order_note`.
- [x] Đảm bảo `has_updates = True` khi clear note.
- [x] Không phụ thuộc vào request có gửi `order_note` hay không.
- [x] Giữ behavior update các field khác như cũ.

Kết quả mong muốn:
  Dashboard chỉ cần PATCH status về `new`, BE tự clear note.

### 3. Response sau update

- [x] Response trả `status = "new"`.
- [x] Response trả `order_note = null`.
- [x] Detail conversation sau update trả `order_note = null`.
- [x] List conversation sau update không còn hiển thị note cũ.

Kết quả mong muốn:
  FE/dashboard thấy trạng thái đã clean ngay sau request update.

### 4. Edge cases

- [x] Nếu conversation đang `new` và PATCH `status = "new"`, không lỗi.
- [x] Nếu conversation đang `order_pending` nhưng `order_note` đã `None`, PATCH `new` vẫn pass.
- [x] Nếu conversation không tồn tại, giữ behavior `404`.
- [x] Nếu status invalid, giữ behavior `400`.

Kết quả mong muốn:
  Lifecycle mới không làm gãy các update conversation hiện có.

## Acceptance criteria

- [x] `order_pending -> new` clear `order_note`.
- [x] Update field khác không clear `order_note`.
- [x] PATCH response trả note đã clear.
- [x] Conversation không tồn tại vẫn trả `404`.
- [x] Status invalid vẫn trả `400`.

## Ghi chú mở

- Nếu sau này cần lưu lịch sử sale đã xử lý note nào, nên tạo collection riêng hoặc audit log riêng thay vì giữ trong `order_note`.
