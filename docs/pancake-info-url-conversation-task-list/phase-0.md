# Task List Phase 0: Chốt giải pháp Pancake info URL

## Mục tiêu

Phase 0 chốt phạm vi và contract tổng thể cho việc lưu `pancake_info_url` vào collection `conversations`. Field này được tạo từ `page_id` và `pancake_conversation_id` của tin nhắn Pancake đầu tiên khi BE tạo conversation mới.

Phase này chỉ chốt giải pháp và ranh giới trách nhiệm. Chưa sửa code, chưa thay đổi schema và chưa thêm test.

## Quyết định cần chốt

- `pancake_info_url` là field optional string trên `Conversation`.
- URL format cố định là `https://pancake.vn/{page_id}?c_id={pancake_conversation_id}`.
- `{page_id}` lấy từ `normalized["page_id"]`, tương ứng `messages.meta.page_id`.
- `{c_id}` lấy từ `normalized["pancake_conversation_id"]`, tương ứng `messages.meta.pancake_conversation_id`.
- Field chỉ được tạo một lần duy nhất khi insert conversation mới.
- Message tiếp theo không overwrite `pancake_info_url`.
- Conversation cũ không có field này vẫn hợp lệ.
- Không backfill conversation cũ trong request xử lý message mới.
- Không thêm biến env mới trong phase này.

## Ngoài phạm vi Phase 0

- Chưa thêm field vào model.
- Chưa thêm field vào response schema.
- Chưa tạo helper build URL.
- Chưa gắn helper vào `_get_or_create_pancake_conversation`.
- Chưa thêm test.
- Chưa viết script backfill conversation cũ.

## File tài liệu liên quan

- [docs/pancake-info-url-conversation.md](../pancake-info-url-conversation.md)
- [docs/pancake-info-url-conversation-task-list/phase-1.md](phase-1.md)
- [docs/pancake-info-url-conversation-task-list/phase-2.md](phase-2.md)
- [docs/pancake-info-url-conversation-task-list/phase-3.md](phase-3.md)
- [docs/pancake-info-url-conversation-task-list/phase-4.md](phase-4.md)

## Checklist

### 1. Chốt field mới

- [x] Xác nhận field tên là `pancake_info_url`.
- [x] Xác nhận field nằm trong collection `conversations`.
- [x] Xác nhận field là optional string.
- [x] Xác nhận conversation cũ không có field này vẫn hợp lệ.
- [x] Xác nhận không cần index cho field này trong phase đầu.

Kết quả mong muốn:
  Schema mới tương thích dữ liệu cũ và không làm tăng chi phí index không cần thiết.

### 2. Chốt format URL

- [x] Xác nhận domain là `https://pancake.vn`.
- [x] Xác nhận path segment dùng `page_id`.
- [x] Xác nhận query param là `c_id`.
- [x] Xác nhận giá trị `c_id` dùng `pancake_conversation_id`.
- [x] Xác nhận không thêm token hoặc auth data vào URL.

Kết quả mong muốn:
  Link mở đúng hội thoại Pancake và không chứa dữ liệu xác thực.

### 3. Chốt thời điểm tạo field

- [x] Xác nhận chỉ tạo `pancake_info_url` khi insert conversation mới.
- [x] Xác nhận không update field khi conversation đã tồn tại.
- [x] Xác nhận không backfill tự động trong webhook request.
- [x] Xác nhận các update hiện tại như `channel`, `customer_name`, `updated_at` vẫn giữ behavior cũ.

Kết quả mong muốn:
  Field được tạo một lần đúng yêu cầu và không bị thay đổi bởi các message sau.

## Acceptance criteria

- [x] Team chốt `pancake_info_url` là optional string.
- [x] Team chốt URL format Pancake.
- [x] Team chốt field chỉ tạo khi create conversation.
- [x] Team chốt không overwrite và không auto-backfill.
- [x] Team chốt không thêm env mới trong phase đầu.

## Ghi chú mở

- Nếu sau này cần đổi domain Pancake hoặc query param, nên mở task riêng để đưa base URL vào config.
- Nếu cần link cho conversation cũ, nên chạy backfill bằng script riêng có kiểm soát.
