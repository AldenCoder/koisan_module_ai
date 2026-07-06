# Task List Phase 1: Bổ sung status handover

## Mục tiêu

Phase 1 chuẩn hóa các giá trị `Conversation.status` cho luồng handover: giữ `new`, thêm/dùng `handover`, giữ `confirmed` để xác nhận handover đã xử lý xong, và gỡ các status không còn dùng là `not_interested`, `highly_interested`.

Hiện collection `conversations` đã có field `status` và default là `new`. Sau phase này, status hợp lệ là `new`, `handover`, `confirmed`.

## Phạm vi thay đổi

- Model enum `ConversationStatus`.
- Public schema enum `ConversationStatusSchema`.
- Logic normalize/validate status trong conversation service.
- Test conversation API/service liên quan đến status.

## File dự kiến thay đổi

- [app/models/conversations.py](../../app/models/conversations.py)
- [app/api/schemas/conversation.py](../../app/api/schemas/conversation.py)
- [app/services/conversation_service.py](../../app/services/conversation_service.py)
- [tests/test_conversations_api.py](../../tests/test_conversations_api.py)

## Checklist

### 1. Update model enum

- [x] Mở [app/models/conversations.py](../../app/models/conversations.py).
- [x] Gỡ `NOT_INTERESTED = "not_interested"` khỏi `ConversationStatus`.
- [x] Gỡ `HIGHLY_INTERESTED = "highly_interested"` khỏi `ConversationStatus`.
- [x] Thêm `HANDOVER = "handover"` vào `ConversationStatus`.
- [x] Giữ `CONFIRMED = "confirmed"` trong `ConversationStatus`.
- [x] Giữ default `ConversationStatus.NEW` cho field `status`.
- [x] Không thêm migration riêng nếu database đang lưu status dạng string và không cần backfill.

Kết quả mong muốn:
  Model Beanie/Pydantic đọc và ghi được document có `status = "handover"`.

### 2. Update API schema enum

- [x] Mở [app/api/schemas/conversation.py](../../app/api/schemas/conversation.py).
- [x] Gỡ `NOT_INTERESTED = "not_interested"` khỏi `ConversationStatusSchema`.
- [x] Gỡ `HIGHLY_INTERESTED = "highly_interested"` khỏi `ConversationStatusSchema`.
- [x] Thêm `HANDOVER = "handover"` vào `ConversationStatusSchema`.
- [x] Giữ `CONFIRMED = "confirmed"` trong `ConversationStatusSchema`.
- [x] Đảm bảo `ConversationCreateRequest.status` vẫn default `NEW`.
- [x] Đảm bảo `ConversationUpdateRequest.status` accept `HANDOVER`.
- [x] Đảm bảo response schema trả được status `handover`.
- [x] Thêm enum filter riêng cho API list conversation, chỉ gồm `new`, `handover`, `confirmed`.

Kết quả mong muốn:
  API conversation có thể nhận và trả `handover` ở create/update/list/detail.

### 3. Update validator status

- [x] Mở [app/services/conversation_service.py](../../app/services/conversation_service.py).
- [x] Kiểm tra `_normalize_conversation_status`.
- [x] Đảm bảo `ConversationStatus("handover")` pass.
- [x] Đảm bảo `ConversationStatus("confirmed")` pass.
- [x] Đảm bảo `not_interested` và `highly_interested` không còn là status hợp lệ.
- [x] Update message lỗi allowed values thành `new, handover, confirmed`.
- [x] Không nới validator thành arbitrary string; vẫn chỉ accept enum hợp lệ.

Kết quả mong muốn:
  Status invalid vẫn bị reject, nhưng `handover` không còn bị reject.

### 4. Update tests cho conversation API

- [x] Thêm hoặc sửa test update conversation với payload `{"status": "handover"}`.
- [x] Test response trả `status == "handover"`.
- [x] Test list/filter conversation theo `status=handover` nếu API list đang support filter status.
- [x] Test enum filter của API list conversation chỉ gồm `new`, `handover`, `confirmed`.
- [x] Test `handover -> confirmed` pass.
- [x] Test `new -> confirmed` bị reject.
- [x] Test `not_interested` và `highly_interested` không còn hợp lệ.
- [x] Test invalid status vẫn trả lỗi như hiện tại.
- [x] Đảm bảo test default status vẫn là `new`.

Kết quả mong muốn:
  Các behavior cũ không regress, status mới được cover.

## Acceptance criteria

- [x] `ConversationStatus.HANDOVER` tồn tại.
- [x] `ConversationStatusSchema.HANDOVER` tồn tại.
- [x] `ConversationStatus.CONFIRMED` tồn tại.
- [x] `ConversationStatusSchema.CONFIRMED` tồn tại.
- [x] `PATCH /api/v1/conversations/{conversation_id}` accept `{"status": "handover"}`.
- [x] `PATCH /api/v1/conversations/{conversation_id}` accept `{"status": "confirmed"}` khi status hiện tại là `handover`.
- [x] List/detail conversation trả được `status = "handover"`.
- [x] List/detail conversation trả được `status = "confirmed"`.
- [x] Invalid status vẫn bị reject.
- [x] `pytest -q` pass.

## Ghi chú mở

- Nếu test dùng enum schema, cần update expected enum thay vì so string tùy pattern test hiện có.
- Nếu dashboard/frontend đang hard-code danh sách status, phần đó nằm ngoài repo/backend task này trừ khi có yêu cầu riêng.
