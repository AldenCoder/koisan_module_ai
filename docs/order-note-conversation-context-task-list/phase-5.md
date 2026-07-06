# Task List Phase 5: Test coverage

## Mục tiêu

Phase 5 bổ sung test cho toàn bộ flow order note và context `conversation_id`. Test phải chạy local bằng `pytest -q`, không cần external service.

Kết quả mong muốn:

- Service append note được cover.
- API order note được cover.
- Status lifecycle clear note được cover.
- AI payload có `conversation_id` được cover.
- Các lỗi `conversation_id` không update DB được cover.

## Đầu vào đã chốt

- Repo dùng Python 3.11.
- Chạy test bằng `pytest -q`.
- Không chạy `pre-commit`.
- Tests không gọi Pancake/Facebook/AI thật.

## Ngoài phạm vi Phase 5

- Không test UI dashboard.
- Không test external AI Agent thật.
- Không test endpoint production thật.
- Không thêm load test.

## File test dự kiến sửa/thêm

- [tests/test_conversations_api.py](../../tests/test_conversations_api.py)
- [tests/test_conversation_status_transitions.py](../../tests/test_conversation_status_transitions.py)
- [tests/test_facebook_webhook_forward.py](../../tests/test_facebook_webhook_forward.py)
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)
- `tests/test_order_notes_api.py`, nếu tách test API riêng.
- `tests/test_order_note_service.py`, nếu tách service riêng.

## Checklist

### 1. Test model/schema conversation

- [x] Test conversation response có `order_note`.
- [x] Test conversation thiếu `order_note` serialize được.
- [x] Test status schema accept `order_pending`.
- [x] Test list filter accept `order_pending` nếu filter được expose.
- [x] Test invalid status vẫn bị reject.

Kết quả mong muốn:
  Schema mới không regression API conversation.

### 2. Test helper format note

- [x] Test note đầu tiên format `1. [HH:mm] ...`.
- [x] Test note thứ hai append `2. [HH:mm] ...`.
- [x] Test note thứ ba append `3. [HH:mm] ...`.
- [x] Test note hiện tại rỗng thì index về `1`.
- [x] Test trim `order_note`.
- [x] Test order note rỗng sau trim bị reject.

Kết quả mong muốn:
  Append text ổn định, không phụ thuộc database.

### 3. Test service create order note

- [x] Test lần đầu set `status = order_pending`.
- [x] Test lần đầu ghi `order_note` dòng `1.`.
- [x] Test lần hai append dòng `2.`.
- [x] Test giữ note cũ khi append note mới.
- [x] Test update `updated_at`.
- [x] Test sai format `conversation_id` không save conversation.
- [x] Test not found không save conversation nào.
- [x] Test not found có warning log.
- [x] Test invalid id có warning log.
- [x] Test không fallback sang conversation khác.

Kết quả mong muốn:
  Service đúng rule id là nguồn định danh duy nhất.

### 4. Test API order note

- [x] Test `POST /api/v1/order-notes` success.
- [x] Test response có `conversation_id`.
- [x] Test response có `status = order_pending`.
- [x] Test response có `order_note_index`.
- [x] Test thiếu `conversation_id` trả lỗi.
- [x] Test thiếu `order_note` trả lỗi.
- [x] Test `order_note` rỗng trả lỗi.
- [x] Test conversation không tồn tại trả `404`.
- [x] Test id sai format trả `400`.
- [x] Test body có field thừa không làm thay đổi contract nếu schema forbid extra.

Kết quả mong muốn:
  API contract đủ chắc cho AI Agent gọi.

### 5. Test clear note khi sale xử lý xong

- [x] Test `order_pending -> new` clear `order_note`.
- [x] Test response sau update có `order_note = None`.
- [x] Test update profile không clear `order_note`.
- [x] Test status giữ `order_pending` không clear `order_note`.
- [x] Test conversation không tồn tại vẫn trả `404`.

Kết quả mong muốn:
  Sale chỉ cần đổi status về `new` để dọn note.

### 6. Test AI payload context

- [x] Test `_build_ai_chat_payload` không truyền `conversation_id` giữ behavior cũ.
- [x] Test `_build_ai_chat_payload` truyền id thì append đúng context note.
- [x] Test init message không append context note.
- [x] Test Pancake `_generate_pancake_reply` truyền `conversation.id`.
- [x] Test Pancake auto consult vẫn truyền `conversation.id`.
- [x] Test Facebook call site nếu được áp dụng.

Kết quả mong muốn:
  AI luôn nhận đúng id khi webhook gọi AI reply path.

### 7. Chạy test tổng

- [x] Chạy `pytest -q`.
- [x] Nếu fail do test cũ cần update expectation, sửa theo behavior mới.
- [x] Không chạy `pre-commit`.
- [x] Ghi lại nếu có test không chạy được vì môi trường local thiếu dependency.

Kết quả mong muốn:
  Test suite pass hoặc có lý do rõ nếu môi trường không chạy được.

## Acceptance criteria

- [x] Test model/schema pass.
- [x] Test service append note pass.
- [x] Test API order note pass.
- [x] Test clear note pass.
- [x] Test AI context pass.
- [x] `pytest -q` pass.

## Ghi chú mở

- Nếu muốn test chống duplicate sau này, cần thêm field idempotency vào contract trước.
