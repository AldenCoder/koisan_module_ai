# Task List Phase 1: Bổ sung model/schema

## Mục tiêu

Phase 1 bổ sung field `pancake_info_url` vào model `Conversation` và response schema nếu API cần trả link này cho client. Field phải optional để không ảnh hưởng các conversation cũ.

Kết quả mong muốn:

- Model `Conversation` có field `pancake_info_url`.
- Conversation cũ thiếu field vẫn load được.
- Response conversation có thể trả `pancake_info_url` nếu field tồn tại.
- API create/update không nhận field này từ client.

## Đầu vào đã chốt

- Field tên là `pancake_info_url`.
- Field là optional string.
- Không cần migration bắt buộc.
- Không cần index.
- Field được tạo bởi webhook Pancake, không nhập tay qua API CRUD conversation.

## Ngoài phạm vi Phase 1

- Không build URL.
- Không gắn vào webhook create conversation.
- Không backfill dữ liệu cũ.
- Không thêm UI/admin.

## File chính dự kiến sửa

- [app/models/conversations.py](../../app/models/conversations.py)
- [app/api/schemas/conversation.py](../../app/api/schemas/conversation.py)
- [tests/test_conversations_api.py](../../tests/test_conversations_api.py)

## Checklist

### 1. Cập nhật model

- [x] Thêm `pancake_info_url` vào `Conversation`.
- [x] Dùng `Optional[str]`.
- [x] Dùng `Field(default=None, max_length=500)`.
- [x] Không thêm index mới.
- [x] Đảm bảo import typing hiện tại vẫn phù hợp.

Kết quả mong muốn:
  Model Beanie nhận field mới nhưng vẫn tương thích document cũ.

### 2. Cập nhật response schema

- [x] Thêm `pancake_info_url` vào `ConversationInfoResponse` nếu cần expose ra client.
- [x] Đảm bảo `ConversationListItemResponse` kế thừa field này.
- [x] Đảm bảo detail response có field này nếu đang dùng `ConversationInfoResponse`.
- [x] Không thêm field vào `ConversationCreateRequest`.
- [x] Không thêm field vào `ConversationUpdateRequest`.

Kết quả mong muốn:
  Client có thể đọc link Pancake nhưng không thể nhập tay field này qua API create/update.

### 3. Test schema/API

- [x] Test response conversation có `pancake_info_url` khi model có field.
- [x] Test conversation thiếu `pancake_info_url` vẫn serialize được.
- [x] Test create request không nhận/set `pancake_info_url`.
- [x] Test update request không nhận/set `pancake_info_url`.

Kết quả mong muốn:
  API không regression và field mới được expose đúng chiều đọc.

## Acceptance criteria

- [x] `Conversation` model có `pancake_info_url`.
- [x] Field optional và default `None`.
- [x] Response schema trả được field nếu tồn tại.
- [x] Create/update request không cho client set field.
- [x] Test phase này pass.

## Ghi chú mở

- Nếu UI chưa dùng field này ngay, vẫn có thể thêm vào response để API contract sẵn sàng cho bước hiển thị sau.
