# Task List Phase 4: Test và rollout

## Mục tiêu

Phase 4 hoàn thiện test và checklist rollout cho thay đổi `pancake_info_url`. Trọng tâm là verify tạo URL đúng, không overwrite field cũ, tương thích conversation cũ và không regression flow Pancake webhook.

Kết quả mong muốn:

- Test unit/helper đầy đủ.
- Test webhook create/reuse conversation đầy đủ.
- Test schema/API conversation không regression.
- Chạy được `pytest -q`.

## Đầu vào đã chốt

- Field optional trên `Conversation`.
- URL chỉ tạo khi insert conversation mới.
- Không backfill tự động.
- Không env mới.

## Ngoài phạm vi Phase 4

- Không test external Pancake thật.
- Không test UI/admin.
- Không chạy pre-commit.
- Không deploy production trong phase này.

## File chính dự kiến sửa

- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)
- [tests/test_conversations_api.py](../../tests/test_conversations_api.py)
- `tests/test_pancake_conversation_link_service.py`, nếu có service riêng.

## Checklist

### 1. Test helper build URL

- [x] Test build URL đúng với `page_id` và `pancake_conversation_id`.
- [x] Test trim khoảng trắng đầu/cuối input.
- [x] Test thiếu `page_id` trả `None`.
- [x] Test thiếu `pancake_conversation_id` trả `None`.
- [x] Test không thêm token hoặc query param khác.

Kết quả mong muốn:
  Helper được cover độc lập, không cần database.

### 2. Test Pancake webhook conversation

- [x] Test conversation mới có `pancake_info_url` đúng format.
- [x] Test conversation mới vẫn lưu đúng `channel`, `customer_name`, `customer_id`.
- [x] Test conversation đã tồn tại không bị overwrite URL.
- [x] Test conversation đã tồn tại và URL `None` không bị backfill.
- [x] Test duplicate message không tạo/update URL lần hai.

Kết quả mong muốn:
  Flow webhook tạo field đúng lúc và không làm lệch các guard hiện tại.

### 3. Test schema/API conversation

- [x] Test list conversation trả `pancake_info_url` nếu field có dữ liệu.
- [x] Test detail conversation trả `pancake_info_url` nếu field có dữ liệu.
- [x] Test conversation cũ thiếu field vẫn serialize được.
- [x] Test create request không set field này.
- [x] Test update request không set field này.

Kết quả mong muốn:
  API expose field theo chiều đọc nhưng không cho client nhập tay.

### 4. Rollout

- [x] Chạy `pytest -q`.
- [x] Kiểm tra log không chứa token.
- [x] Kiểm tra không cần migration bắt buộc trước deploy.
- [x] Ghi chú nếu muốn backfill conversation cũ thì mở script riêng.

Kết quả mong muốn:
  Thay đổi đủ nhỏ để rollout cùng code webhook hiện tại.

## Acceptance criteria

- [x] Test helper pass.
- [x] Test webhook pass.
- [x] Test conversation API/schema pass.
- [x] `pytest -q` pass.
- [x] Không cần pre-commit theo guideline repo.

## Ghi chú mở

- Nếu môi trường local không có command `pytest`, chạy bằng Python trong venv tương ứng, ví dụ `.venv/bin/python -m pytest -q`.
